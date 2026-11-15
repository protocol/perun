#!/usr/bin/env python3
"""Frozen, zero-model-spend bench for the review_checks.sh hub.

Copies bench/tool-only/{vuln,clean} into a throwaway git repo, runs `review_checks.sh --full`, and prints JSON:
per-CWE recall, overall recall, and false positives (rows on the clean twins). A row hits an answer.json entry
when it is in the same file and on the seeded line (+/-2), or is a file-level row (line 0, e.g. a dependency
CVE). Rows of tool `not-checked` are unchecked surface, not findings, and are ignored.

Exit 0 pass or SKIP (a core tool is absent: the floors are measured with every tool installed, as in the ci.yml
real-hub job), 1 when recall < FLOOR_RECALL or false positives > MAX_FALSE_POSITIVES.
Raise the floor only after a measured improvement in CI; never lower it to make a run pass. Side effects: temp dir only.
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HUB = ROOT / ".claude/skills/deep-code-review/scripts/review_checks.sh"
CORE = ("semgrep", "gitleaks", "trivy", "git", "jq")
FLOOR_RECALL = 1.0  # frozen: 11/11 measured locally with semgrep, gitleaks, trivy, bandit, ruff; confirm on the first CI run
MAX_FALSE_POSITIVES = 8  # frozen: 8 noise rows on the clean twins (bandit B404/B603/B607, ruff S603/S607, trivy AWS-0090/0132, semgrep path-traversal)


def run(truth_path=ROOT / "bench/tool-only/answer.json", fixtures=ROOT / "bench/tool-only"):
    truth = {k: v for k, v in json.loads(Path(truth_path).read_text()).items() if k != "note"}
    with tempfile.TemporaryDirectory() as t:
        for d in ("vuln", "clean"):
            shutil.copytree(fixtures / d, Path(t) / d)
        g = ["git", "-c", "user.name=b", "-c", "user.email=b@example.com"]
        for a in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "bench"]):
            subprocess.run(g + a, cwd=t, check=True, capture_output=True)
        out = subprocess.run(["bash", str(HUB), "--full"], cwd=t, capture_output=True, text=True).stdout
    rows = [r for r in json.loads(out or "[]") if r.get("tool") != "not-checked" and r.get("rule") != "not-checked"]
    found, per = set(), {}
    for key, cwe in truth.items():
        f, _, line = key.rpartition(":")
        hit = any(r["file"] == f and (r["line"] == 0 or abs(r["line"] - int(line)) <= 2) for r in rows)
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
        return 0
    res = run()
    print(json.dumps(res, indent=2))
    bad = res["recall"] < float(os.environ.get("BENCH_FLOOR_RECALL", FLOOR_RECALL)) or \
        res["false_positives"] > int(os.environ.get("BENCH_MAX_FP", MAX_FALSE_POSITIVES))
    if bad:
        print("FAIL bench_tool_only: recall %s (floor %s), false positives %s (max %s)" % (
            res["recall"], FLOOR_RECALL, res["false_positives"], MAX_FALSE_POSITIVES), file=sys.stderr)
    return int(bad)


if __name__ == "__main__":
    sys.exit(main())
