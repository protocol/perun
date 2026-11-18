#!/usr/bin/env python3
"""Frozen, zero-model-spend bench for the review_checks.sh hub.

Copies bench/tool-only/{vuln,clean} into a throwaway git repo, runs `review_checks.sh --full`, and prints JSON:
per-CWE recall, overall recall, and false positives (rows on the clean twins). A row hits an answer.json entry
when it is in the same file and on the seeded line (+/-2) and its rule is not a noise rule (one that also fires on
the clean twins), or is a file-level row (line 0) on the dependency fixture only. Rows of tool `not-checked` are unchecked surface, not findings, and are ignored.

Exit 0 pass or SKIP (a core tool is absent: the floors are measured with every tool installed, as in the ci.yml
real-hub job), 1 on SKIP when REQUIRE_REAL_HUB=1 (CI), 1 when recall < FLOOR_RECALL or false positives > MAX_FALSE_POSITIVES.
Raise the floor only after a measured improvement in CI; never lower it to make a run pass. The false-positive ceiling is a ratchet: a run above it fails, a run below it prints a NOTE to lower it, and it is never raised. Side effects: temp dir only.
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HUB = ROOT / ".claude/skills/deep-code-review/scripts/review_checks.sh"
CORE = ("semgrep", "gitleaks", "trivy", "bandit", "ruff", "git", "jq")
FLOOR_RECALL = 1.0  # frozen: 11/11 measured in the CI real-hub job after the CWE-22 taint rule stopped firing on send_from_directory's file name
LINT_TOOLS = ("ruff", "pyflakes")  # style linters (ruff's PIE and the like), not security scanners: their clean-twin rows are reported as lint_rows, never counted as security false positives. Secret rows the hub demoted to a likely-fixture hint are reported as demoted_rows, not counted either. ruff-security (the S rules) is a scanner and stays counted.
DEP_FILE = "vuln/requirements.txt"  # only fixture where a file-level (line 0) row counts
MAX_DEMOTED_ROWS = 6  # new in this PR: ceiling on secret rows the hub demoted on the clean twins (demotion keeps the row, so it must not hide a false positive). Ratchet: lower it, never raise it. Measured 6 rows with both scanners: the placeholder lines in clean/demoted.env are hit by detect-secrets (3) and trufflehog (2), plus the linkedin row; without detect-secrets it is 3.
MAX_FALSE_POSITIVES = 25  # frozen: 22 noise rows measured in the CI real-hub job on #2390 (gosec and Go rows are not measurable locally) + 3 from the ssrf_redirect twin (registry django and flask rules, perun.py.ssrf)


def run(truth_path=ROOT / "bench/tool-only/answer.json", fixtures=ROOT / "bench/tool-only"):
    truth = {k: v for k, v in json.loads(Path(truth_path).read_text()).items() if k != "note"}
    with tempfile.TemporaryDirectory() as t:
        for d in ("vuln", "clean"):
            shutil.copytree(fixtures / d, Path(t) / d)
        # generated here so no committed text matches a secret pattern; keep on line 2 (answer.json: vuln/secret.py:2)
        (Path(t) / "vuln/secret.py").write_text("# Fictional credential for a bench fixture; not a real account.\nAPI_KEY = \"" + "q7Zk2XvB9mWc4T" + "nRj8LpD3sHf6YgA1eU" + "\"\n")
        # look-alike secrets the hub demotes to a likely-fixture hint; built here so no committed text matches a secret pattern. Fictional hosts and values only.
        hx, uu, pw = "0123456789abcdef" * 2 + "01234567", "123e4567-e89b-12d3-a456-426614174000", "Zq8v" + "3Lr2"
        (Path(t) / "clean/demoted.env").write_text(f"DB=postgres://user:pass@db.internal:5432/app\nMONGO=mongodb://root:example@db.internal/app\nLOCAL=postgres://svc:changeme@localhost/app\nsource_id={uu}\n")
        (Path(t) / "clean/demoted.yml").write_text(f"steps:\n  - uses: acme/setup@{hx}\n")
        (Path(t) / "clean/package-lock.json").write_text('{\n  "integrity": "sha512-' + hx + '"\n}\n')
        (Path(t) / "clean/demoted.conf").write_text("linkedin_" + "client_id = linkedinClient\n")  # joined so no source line matches gitleaks
        (Path(t) / "go.mod").write_text("module bench\n\ngo 1.21\n")  # gosec/staticcheck need a root module for the .go twins
        g = ["git", "-c", "user.name=b", "-c", "user.email=b@example.com"]
        for a in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "bench"]):
            subprocess.run(g + a, cwd=t, check=True, capture_output=True)
        # Real-scanner bench: read the host tool caches too. scrub_env.sh points DCR_CACHE_ROOT at an empty dir,
        # which leaves semgrep without its p/default snapshot (bundled rules only) and fails recall for no code reason.
        env = {k: v for k, v in os.environ.items() if k != "DCR_CACHE_ROOT"}
        out = subprocess.run(["bash", str(HUB), "--full"], cwd=t, capture_output=True, text=True, env=env).stdout
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
    clean = [r for r in rows if r["file"].startswith("clean/")]
    dem = sorted({(r["file"], r["line"], r["rule"]) for r in clean if r.get("hint") == "likely-fixture"})  # secret rows the hub demoted (kept, never dropped): triage-low, not counted
    fps = sorted({(r["file"], r["line"], r["rule"]) for r in clean if r["tool"] not in LINT_TOOLS and r.get("hint") != "likely-fixture"})
    lint = sorted({(r["file"], r["line"], r["rule"]) for r in clean if r["tool"] in LINT_TOOLS})
    return {"recall": round(len(found) / len(truth), 3), "hits": len(found), "total": len(truth),
            "per_cwe_recall": {c: h / n for c, (h, n) in sorted(per.items())},
            "missed": sorted(set(truth) - found), "false_positives": len(fps),
            "false_positive_rows": [list(x) for x in fps], "lint_rows": [list(x) for x in lint], "demoted_rows": [list(x) for x in dem]}


def main():
    if not HUB.exists() or any(shutil.which(c) is None for c in CORE):
        print("SKIP bench_tool_only: " + ", ".join(c for c in CORE if shutil.which(c) is None) + " not installed")
        return int(os.environ.get("REQUIRE_REAL_HUB") == "1")
    res = run()
    print(json.dumps(res, indent=2))
    bad = res["recall"] < FLOOR_RECALL or \
        res["false_positives"] > MAX_FALSE_POSITIVES or len(res["demoted_rows"]) > MAX_DEMOTED_ROWS
    if bad:
        print("FAIL bench_tool_only: recall %s (floor %s), false positives %s (max %s)" % (
            res["recall"], FLOOR_RECALL, res["false_positives"], MAX_FALSE_POSITIVES), file=sys.stderr)
    if len(res["demoted_rows"]) > MAX_DEMOTED_ROWS:
        print("FAIL bench_tool_only: demoted rows %s (max %s)" % (len(res["demoted_rows"]), MAX_DEMOTED_ROWS), file=sys.stderr)
    elif len(res["demoted_rows"]) < MAX_DEMOTED_ROWS:
        print("NOTE bench_tool_only: demoted rows %s are below the ceiling %s; lower MAX_DEMOTED_ROWS to %s (never raise it)" % (
            len(res["demoted_rows"]), MAX_DEMOTED_ROWS, len(res["demoted_rows"])), file=sys.stderr)
    if res["false_positives"] < MAX_FALSE_POSITIVES:  # ratchet: the ceiling only ever goes down
        print("NOTE bench_tool_only: false positives %s are below the ceiling %s; lower MAX_FALSE_POSITIVES to %s (never raise it)" % (
            res["false_positives"], MAX_FALSE_POSITIVES, res["false_positives"]), file=sys.stderr)
    return int(bad)


if __name__ == "__main__":
    sys.exit(main())
