"""Tests for the committed G1 held-out sets and their results.

Covers: the scorer's sha256 pin, the per-file sha256 record in each result.json
against the committed set files, and the internal consistency of the scored
counts (tp, reports, precision, recall) against per_case rows.

Side effects: reads files under docs/bench/g1-matrix/heldout/ only.
Edge cases: a missing set file or a hash drift fails the test (fail closed).
"""

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELDOUT = ROOT / "docs" / "bench" / "g1-matrix" / "heldout"
SCORER_SHA256 = "bb55c8d12338a2b2b7809026ca07aec6ab8a6f4f96b3cdc2babf217b58eacc96"
SETS = ("api1", "api3", "api5", "api10")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(set_name: str) -> dict:
    return json.loads((HELDOUT / set_name / "result.json").read_text(encoding="utf-8"))


class ScorerPinTest(unittest.TestCase):
    def test_scorer_sha256_pinned(self):
        self.assertEqual(_sha256(HELDOUT / "score.py"), SCORER_SHA256)


class SetHashTest(unittest.TestCase):
    def test_every_recorded_hash_matches_committed_file(self):
        for name in SETS:
            with self.subTest(set=name):
                result = _load(name)
                self.assertTrue(result["set_sha256"], "no hashes recorded")
                for rel, digest in result["set_sha256"].items():
                    path = HELDOUT / name / rel
                    self.assertTrue(path.is_file(), f"missing committed file {rel}")
                    self.assertEqual(_sha256(path), digest, f"hash drift: {rel}")

    def test_committed_set_has_no_unrecorded_case_files(self):
        for name in SETS:
            with self.subTest(set=name):
                recorded = set(_load(name)["set_sha256"])
                on_disk = {
                    p.relative_to(HELDOUT / name).as_posix()
                    for p in (HELDOUT / name / "cases").rglob("*")
                    if p.is_file()
                }
                on_disk.add("cases.json")
                self.assertEqual(on_disk, recorded)


class ScoreConsistencyTest(unittest.TestCase):
    def test_counts_match_per_case(self):
        for name in SETS:
            with self.subTest(set=name):
                r = _load(name)
                rows = r["per_case"]
                positives = [row for row in rows if row["kind"] == "pos"]
                tp = sum(1 for row in positives if row["tp"])
                reports = sum(len(row["reports"]) for row in rows)
                self.assertEqual(r["cases"], len(rows))
                self.assertEqual(r["positives"], len(positives))
                self.assertEqual(r["tp"], tp)
                self.assertEqual(r["reports"], reports)
                self.assertEqual(r["precision"], round(tp / reports, 3))
                self.assertEqual(r["recall"], round(tp / len(positives), 3))


def _load_audit():
    """Import audit.py by path. Offline: importing it only defines functions and constants."""
    spec = importlib.util.spec_from_file_location("g1_audit", HELDOUT / "audit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AUDIT = _load_audit()

SYNTHETIC_YML = """rules:
- id: perun.js.mass-assignment
  message: js mass assignment
  languages: [js]
- id: perun.js.sql-injection
  message: js sql injection
  languages: [js]
- id: perun.py.mass-assignment
  message: py mass assignment
  languages: [python]
- id: perun.py.path-traversal
  message: py path traversal
  languages: [python]
"""


class AuditHelpersTest(unittest.TestCase):
    def test_only_rules_keeps_exactly_the_matching_blocks_verbatim(self):
        expected = (
            "- id: perun.js.mass-assignment\n  message: js mass assignment\n  languages: [js]\n"
            "- id: perun.py.mass-assignment\n  message: py mass assignment\n  languages: [python]\n"
        )
        self.assertEqual(AUDIT.only_rules(SYNTHETIC_YML, "mass-assignment"), expected)

    def test_section_returns_item_up_to_next_heading(self):
        md = "# Title\n\n## API1 Other\nalpha\n\n## API3 Object Property\nbeta\ngamma\n\n## API5 Last\ndelta\n"
        self.assertEqual(AUDIT.section(md, "api3"), "## API3 Object Property\nbeta\ngamma\n\n")

    def test_section_empty_when_absent(self):
        md = "# Title\n\n## API1 Other\nalpha\n\n## API5 Last\ndelta\n"
        self.assertEqual(AUDIT.section(md, "api3"), "")


if __name__ == "__main__":
    unittest.main()
