#!/usr/bin/env python3
"""Frozen, zero-model-spend bench for the review_checks.sh hub.

Copies bench/tool-only/{vuln,clean} into a throwaway git repo, runs `review_checks.sh --full`, and prints JSON:
per-CWE recall, overall recall, and false positives (rows on the clean twins). A row hits an answer.json entry
when it is in the same file and on the seeded line (+/-2) and its rule is not a noise rule (one that also fires on
the clean twins), or is a file-level row (line 0) on the dependency fixture only. Rows of tool `not-checked` are unchecked surface, not findings, and are ignored.

Exit 0 pass or SKIP (a core tool is absent: the floors are measured with every tool installed, as in the ci.yml
real-hub job), 1 on SKIP when REQUIRE_REAL_HUB=1 (CI), 1 when recall < FLOOR_RECALL or false positives > MAX_FALSE_POSITIVES.
Raise the floor only after a measured improvement in CI; never lower it to make a run pass. Side effects: temp dir only.
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HUB = ROOT / ".claude/skills/deep-code-review/scripts/review_checks.sh"
CORE = ("semgrep", "gitleaks", "trivy", "bandit", "ruff", "git", "jq")
FLOOR_RECALL = 0.909  # frozen: 10/11 measured locally with semgrep, gitleaks, trivy, bandit, ruff; CWE-22 is caught only by a rule that also fires on its clean twin, so it no longer counts
DEP_FILE = "vuln/requirements.txt"  # only fixture where a file-level (line 0) row counts
MAX_FALSE_POSITIVES = 27  # frozen: 27 noise rows on the clean twins measured in the CI real-hub job (full hub: bandit, ruff, trivy, checkov, devskim, semgrep); a local run with fewer tools sees fewer


def run(truth_path=ROOT / "bench/tool-only/answer.json", fixtures=ROOT / "bench/tool-only"):
    truth = {k: v for k, v in json.loads(Path(truth_path).read_text()).items() if k != "note"}
    with tempfile.TemporaryDirectory() as t:
        for d in ("vuln", "clean"):
            shutil.copytree(fixtures / d, Path(t) / d)
        # generated here so no committed text matches a secret pattern; keep on line 2 (answer.json: vuln/secret.py:2)
        (Path(t) / "vuln/secret.py").write_text("# Fictional credential for a bench fixture; not a real account.\nAPI_KEY = \"" + "q7Zk2XvB9mWc4T" + "nRj8LpD3sHf6YgA1eU" + "\"\n")
        g = ["git", "-c", "user.name=b", "-c", "user.email=b@example.com"]
        for a in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "bench"]):
            subprocess.run(g + a, cwd=t, check=True, capture_output=True)
        out = subprocess.run(["bash", str(HUB), "--full"], cwd=t, capture_output=True, text=True).stdout
    rows = [r for r in json.loads(out or "[]") if r.get("tool") != "not-checked" and r.get("rule") != "not-checked"]
    noise = {r["rule"] for r in rows if r["file"].startswith("clean/")}  # rules that also fire on clean twins prove nothing
    found, per = set(), {}
    for key, cwe in truth.items():
        f, _, line = key.rpartition(":")
        hit = any(r["file"] == f and r["rule"] not in noise and
                  (abs(r["line"] - int(line)) <= 2 or (r["line"] == 0 and f == DEP_FILE)) for r in rows)
        per.setdefault(cwe, [0, 0])[1] += 1
        if hit:
            found.add(key); per[cwe][0] += 1
    fps = sorted({(r["file"], r["line"], r["rule"]) for r in rows if r["file"].startswith("clean/")})
    return {"recall": round(len(found) / len(truth), 3), "hits": len(found), "total": len(truth),
            "per_cwe_recall": {c: h / n for c, (h, n) in sorted(per.items())},
            "missed": sorted(set(truth) - found), "false_positives": len(fps),
            "false_positive_rows": [list(x) for x in fps]}


def main():
    if not HUB.exists() or any(shutil.which(c) is None for c in CORE):
        print("SKIP bench_tool_only: " + ", ".join(c for c in CORE if shutil.which(c) is None) + " not installed")
        return int(os.environ.get("REQUIRE_REAL_HUB") == "1")
    res = run()
    print(json.dumps(res, indent=2))
    bad = res["recall"] < FLOOR_RECALL or \
        res["false_positives"] > MAX_FALSE_POSITIVES
    if bad:
        print("FAIL bench_tool_only: recall %s (floor %s), false positives %s (max %s)" % (
            res["recall"], FLOOR_RECALL, res["false_positives"], MAX_FALSE_POSITIVES), file=sys.stderr)
    return int(bad)


if __name__ == "__main__":
    sys.exit(main())
