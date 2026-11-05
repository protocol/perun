"""Tests for the committed G1 held-out sets and their results.

Covers: the scorer's sha256 pin, the per-file sha256 record in each result.json
against the committed set files, and the internal consistency of the scored
counts (tp, reports, precision, recall) against per_case rows.

Side effects: reads files under docs/bench/g1-matrix/heldout/ only.
Edge cases: a missing set file or a hash drift fails the test (fail closed).
"""

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELDOUT = ROOT / "docs" / "bench" / "g1-matrix" / "heldout"
SCORER_SHA256 = "1224864eaf779a677e267a2ab107f27cad3302cf31471fee15f2604dd6e64d42"
SETS = ("api3", "api5")


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


if __name__ == "__main__":
    unittest.main()
