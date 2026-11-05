#!/usr/bin/env python3
"""Tests for docs/bench/g1-matrix/ablate.py: stripped text, scorer, run order/stop rule/confirmation (fake `claude` on PATH), fail-closed cap and quota."""
import contextlib
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
ABL = ROOT / "docs/bench/g1-matrix/ablate.py"
sys.path.insert(0, str(ROOT / "docs/bench/g1-matrix"))
import ablate  # noqa: E402

EVALS = json.loads(ablate.EVALS.read_text())
BY = {e["id"]: e for e in EVALS}
TERMS = r"IDOR|BOLA|BFLA|mass assignment|over-posting|allow-list of bindable fields|privileged verb|upstream response"

FAKE = r'''#!/usr/bin/env python3
import json, os, sys
a = sys.argv
sysm = a[a.index("--system-prompt") + 1]
usr = sys.stdin.read()
ev = json.load(open(os.environ["FAKE_EVALS"]))
arm = "step" if "two-principal matrix" in sysm else "stripped"
cur = next((e for e in ev if all(open(os.path.join(os.environ["FAKE_FIX"], e["dir"], f)).read() in usr
                                 for f in os.listdir(os.path.join(os.environ["FAKE_FIX"], e["dir"])))), None)
if cur:
    open(os.environ["FAKE_LOG"], "a").write(f"{arm} {cur['id']}\n")
else:
    open(os.environ["FAKE_LOG"], "a").write("preflight\n")
mode = os.environ["FAKE_MODE"]
ideal = [{"file": t["file"], "line": t["line"], "owasp_api_2023": cur["item"]} for t in cur.get("truth", [])] if cur else []
bad = [{"file": "x", "line": 1, "owasp_api_2023": cur["item"]}] if cur and cur["kind"] == "neg" else []
if not cur: out = []
elif arm == "step": out = ideal
elif mode == "all-ideal" or (mode == "mixed" and cur["item"] == "API1"): out = ideal
else: out = bad
text = "OK" if not cur else "review\n```json\n" + json.dumps(out) + "\n```"
if os.environ.get("FAKE_NOQUOTA") != "1":
    print(json.dumps({"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {"w": {"utilization": 0.1}}}}))
print(json.dumps({"type": "result", "result": text, "total_cost_usd": 0.01}))
'''


class Strip(unittest.TestCase):
    def test_stripped_has_no_step_terms_and_differs_only_by_paragraphs(self):
        ref = ablate.REF.read_text()
        s = ablate.stripped(ref)
        self.assertIsNone(re.search(TERMS, s, re.I))
        self.assertIsNotNone(re.search(TERMS, ref, re.I))
        paras = [p for p in ref.split("\n\n") if p.startswith(ablate.LEADS)]
        self.assertEqual(len(paras), 3)
        self.assertEqual(s, "\n\n".join(p for p in ref.split("\n\n") if p not in paras))
        self.assertEqual(len(ref) - len(s), sum(len(p) + 2 for p in paras))

    def test_model_is_sonnet(self):
        self.assertEqual(ablate.R.CLAUDE_MODEL, "sonnet")


class Score(unittest.TestCase):
    def blk(self, items):
        return "x\n```json\n" + json.dumps(items) + "\n```"

    def test_pos_neg_unparseable(self):
        pos, neg = BY["api1-a"], BY["api1-c"]
        good = [{"file": "orders.js", "line": 1, "owasp_api_2023": "API1"}]
        self.assertTrue(ablate.score(self.blk(good), pos))
        self.assertTrue(ablate.score(self.blk([{"file": "d/orders.js", "owasp_api_2023": "API1:2023"}]), pos))
        self.assertFalse(ablate.score(self.blk([{"file": "orders.js", "owasp_api_2023": "API3"}]), pos))
        self.assertFalse(ablate.score(self.blk([{"file": "other.js", "owasp_api_2023": "API1"}]), pos))
        self.assertFalse(ablate.score("no block", pos))
        self.assertFalse(ablate.score("```json\n{bad\n```", pos))
        self.assertTrue(ablate.score("no block", neg))  # unparseable = no findings
        self.assertTrue(ablate.score(self.blk([{"file": "a", "owasp_api_2023": "API3"}]), neg))
        self.assertFalse(ablate.score(self.blk(good), neg))
        self.assertFalse(ablate.score(self.blk([{"owasp_api_2023": "API10"}]), BY["api10-c"]))


class Run(unittest.TestCase):
    def go(self, mode, cap="15", noquota=False):
        td = tempfile.TemporaryDirectory(prefix="g1ab-")
        self.addCleanup(td.cleanup)
        d = td.name
        fake = Path(d) / "bin/claude"
        fake.parent.mkdir()
        fake.write_text(FAKE)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        env = dict(os.environ, PATH=f"{fake.parent}:{os.environ['PATH']}", FAKE_MODE=mode, FAKE_LOG=f"{d}/log", FAKE_EVALS=str(ablate.EVALS),
                   FAKE_FIX=str(ablate.HERE / "evals-b"), FAKE_NOQUOTA="1" if noquota else "0")
        p = subprocess.run([sys.executable, str(ABL), "run", "--out", f"{d}/out", "--cap", cap], env=env, capture_output=True, text=True)
        log = Path(f"{d}/log").read_text().split("\n")[:-1] if Path(f"{d}/log").exists() else []
        res = json.loads(Path(f"{d}/out/result.json").read_text()) if Path(f"{d}/out/result.json").exists() else None
        return p, log, res

    def test_all_ideal_stops_after_stripped(self):
        p, log, res = self.go("all-ideal")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(log[0], "preflight")
        self.assertEqual(log[1:], [f"stripped {e['id']}" for e in EVALS])
        self.assertTrue(all(v.startswith("not_b") for v in res["verdict"].values()))

    def test_order_stop_rule_and_confirmation(self):
        p, log, res = self.go("mixed")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(log[1:13], [f"stripped {e['id']}" for e in EVALS])
        self.assertFalse([x for x in log if x.startswith("step api1-")])  # API1 stripped passes all: no step calls
        self.assertEqual(res["verdict"]["API1"], "not_b: stripped arm passes every fixture")
        for it in ("API3", "API5", "API10"):
            self.assertEqual(res["verdict"][it], "b")
            for e in (x for x in EVALS if x["item"] == it):  # every fixture is a candidate: 1+2 calls per arm
                self.assertEqual(log.count(f"step {e['id']}"), 3)
                self.assertEqual(log.count(f"stripped {e['id']}"), 3)
        step_first = log.index("step api3-a")
        self.assertGreater(step_first, 12)
        self.assertGreater(res["spent"], 0)
        self.assertTrue(all("util" in c for c in res["calls"]))

    def test_cap_fails_closed(self):
        p, log, res = self.go("mixed", cap="0.3")
        self.assertEqual(p.returncode, 3)
        self.assertEqual(log, ["preflight"])
        self.assertEqual(res["exit"], 3)

    def test_missing_quota_fails_closed(self):
        p, log, res = self.go("mixed", noquota=True)
        self.assertEqual(p.returncode, 3)
        self.assertEqual(log, ["preflight"])


class SetAndFreeze(unittest.TestCase):
    def tearDown(self):
        ablate.use_set("evals-b")

    def test_default_set_is_evals_b(self):
        self.assertEqual(ablate.EVALS, ablate.HERE / "evals-b/evals.json")
        ablate.main(["score", "/dev/null", "api1-c"])
        self.assertEqual(ablate.SET, "evals-b")

    def test_set_b2_reads_b2_evals(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ablate, "HERE", Path(d)):
            (Path(d) / "evals-b2").mkdir()
            (Path(d) / "evals-b2/evals.json").write_text(json.dumps([{"id": "z-1", "item": "API1", "kind": "neg", "dir": "z"}]))
            with contextlib.redirect_stdout(io.StringIO()) as out:
                ablate.main(["--set", "evals-b2", "score", "/dev/null", "z-1"])
            self.assertEqual(ablate.EVALS, Path(d) / "evals-b2/evals.json")
            self.assertEqual(out.getvalue().strip(), "pass")

    def freeze(self, text, name):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ablate, "ABLATION", Path(d) / "A.md"), contextlib.ExitStack() as st:
            (Path(d) / "A.md").write_text(text)
            if name == "evals-b2":  # no real b2 set required: fake tree
                (Path(d) / name / "fixtures/x").mkdir(parents=True)
                (Path(d) / name / "evals.json").write_text("[]")
                (Path(d) / name / "fixtures/x/f.js").write_text("1")
                st.enter_context(mock.patch.object(ablate, "HERE", Path(d)))
            with contextlib.redirect_stdout(io.StringIO()):
                ablate.main(["--set", name, "freeze"])
            return (Path(d) / "A.md").read_text()

    def test_freeze_keeps_following_sections(self):
        doc = "# T\n\n## Frozen inputs\nold\n\n## Result\nr\n\n## Frozen inputs (b2)\nkeep\n\n## Next path\nn\n"
        out = self.freeze(doc, "evals-b")
        self.assertNotIn("old", out)
        self.assertTrue(out.startswith("# T\n\n## Frozen inputs\n| Input | Value |"))
        self.assertTrue(out.endswith("\n\n## Result\nr\n\n## Frozen inputs (b2)\nkeep\n\n## Next path\nn\n"))

    def test_freeze_b2_replaces_only_b2_and_appends_when_missing(self):
        out = self.freeze("## Frozen inputs\nb\n\n## Frozen inputs (b2)\nold\n\n## Next path\nn\n", "evals-b2")
        self.assertTrue(out.startswith("## Frozen inputs\nb\n\n## Frozen inputs (b2)\n| Input"))
        self.assertTrue(out.endswith("\n\n## Next path\nn\n"))
        self.assertNotIn("old", out)
        out = self.freeze("# T\n\n## Result\nr\n", "evals-b2")
        self.assertTrue(out.startswith("# T\n\n## Result\nr\n\n## Frozen inputs (b2)\n| Input"))


class FrozenB2(unittest.TestCase):
    """The committed evals-b2 set matches the hashes frozen in ABLATION.md and is shaped 3 pos + 2 neg per item."""

    B2 = ROOT / "docs/bench/g1-matrix/evals-b2"

    def test_frozen_hashes_match_disk(self):
        doc = (ROOT / "docs/bench/g1-matrix/ABLATION.md").read_text()
        sec = doc.split("## Frozen inputs (b2)\n", 1)[1].split("\n## ", 1)[0]
        want = dict(re.findall(r"^\| (?:fixture )?`([^`]+)` sha256 \| ([0-9a-f]{64}) \|$", sec, re.M))
        want.pop("ablate.py")  # the harness itself, not a b2 input
        got = {"evals.json": hashlib.sha256((self.B2 / "evals.json").read_bytes()).hexdigest()}
        for f in (self.B2 / "fixtures").rglob("*"):
            if f.is_file():
                got[f.relative_to(self.B2).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
        self.assertEqual(want, got)

    def test_three_pos_two_neg_per_item_and_truth_exists(self):
        kinds = {}
        for e in json.loads((self.B2 / "evals.json").read_text()):
            kinds.setdefault(e["item"], []).append(e["kind"])
            for t in e.get("truth", []):
                lines = (self.B2 / e["dir"] / t["file"]).read_text().splitlines()
                self.assertTrue(1 <= t["line"] <= len(lines), (e["id"], t))
        self.assertTrue(kinds)
        for item, ks in kinds.items():
            self.assertEqual((ks.count("pos"), ks.count("neg")), (3, 2), item)


if __name__ == "__main__":
    unittest.main()
