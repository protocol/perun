#!/usr/bin/env python3
"""G10 scorer: IaC / CI / secrets detection on set1 (blind truth written by another author; never edited here).

Usage: run_and_score.py [--out DIR] [--detector REPO] [--set DIR]   (DIR under this folder, default set1)
  Builds set1/build.py into a $TMPDIR target, runs `review_checks.sh --repo FIXTURE --full` on each fixture
  (same invocation as docs/bench/g5-currency/run_and_score.py), parses stdout rows into (file, line, tool, rule),
  scores, writes results-<UTC>/score.json (refuses an existing --out). The run is the ONE scored attempt:
  the self-test (test_run_and_score.py) uses synthetic truth only and never touches set1.

SCORING RULES (fixed before any scored run):
  1. Positive hit: any finding row on the same file within +-3 lines of the truth line; a file-level row
     (line <= 0, e.g. a missing-USER finding) matches any truth row on that file. A history-only
     positive (history: true) is hit by any finding that names its path (file == path or path in the row text)
     or its introducing commit (the sha of the commit that added the path, full or >=7-char prefix, in the row text).
  2. Decoy false positive: any finding row on a decoy's file within +-3 lines, file-level rows included
     (history decoys: same path-or-commit test as rule 1). One FP per distinct decoy flagged, however many rows
     flag it (symmetric with one hit per positive).
  3. Control fixture ("control"): any finding row from an IaC, CI or secrets tool is a FP, counted per distinct (file, line). Those tools are
     gitleaks, trufflehog, zizmor, actionlint, hadolint, checkov, trivy*, tfsec, tflint, kube-linter, kubeconform, kubescape.
  4. `not-checked` rows are never findings. Rows from a tool listed under "NOT RUN:" on stderr are ignored
     (never a hit), so the positives they would have covered are misses.
  5. recall = hits/positives; precision = TP/(TP+FP) with TP = hits (1.0 if TP+FP == 0); Wilson 95% lower bound
     reported for both. PASS = recall >= 0.80 AND precision >= 0.80 (point estimates).
  A tool that times out yields no rows ("timeout" recorded in score.json), so its positives are misses; a
  build failure aborts before scoring.
  A row inside +-3 of both a positive and a decoy on one file counts as both a hit and an FP.
"""
import datetime, json, math, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RC = ".claude/skills/deep-code-review/scripts/review_checks.sh"
CONTROL = "control"
IAC_TOOLS = ("gitleaks", "trufflehog", "zizmor", "actionlint", "hadolint", "checkov", "trivy", "tfsec", "tflint",
             "kube-linter", "kubeconform", "kubescape")
WINDOW = 3


def wilson_lower(k, n, z=1.959964):
    """Wilson score 95% lower bound for k successes of n; 0.0 when n == 0."""
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    return max(0.0, (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d)


def parse_rows(stdout):
    """review_checks stdout JSON -> deduped [(file, line, tool, rule)]; invalid JSON -> []. not-checked rows dropped."""
    try:
        rows = json.loads(stdout)
    except ValueError:
        return []
    seen, out = set(), []
    for r in rows:
        k = (r.get("file", ""), int(r.get("line") or 0), r.get("tool", ""), r.get("rule", ""))
        if k[3] != "not-checked" and k not in seen:
            seen.add(k)
            out.append(k + (r.get("text", r.get("message", "")),))
    return out


def parse_not_run(stderr):
    """'review_checks: NOT RUN: a (why), b p/x (why)' -> {'a', 'b'} (first token of each entry)."""
    m = re.search(r"NOT RUN: (.*)", stderr)
    if not m or m[1].strip() == "none":
        return set()
    return {e.split()[0] for e in re.split(r"\)\s*,\s*", m[1]) if e.split()}


def names(row, path, commit):
    """History match: row names the path or the introducing commit."""
    f, _, _, _, text = row
    hay = f + "\n" + text
    return path in hay or bool(commit and any(commit[:n] in hay for n in (40, 7) if len(commit) >= n))


def matches(row, t, commit):
    if t.get("history"):
        return names(row, t["file"], commit)
    return row[0] == t["file"] and (row[1] <= 0 or abs(row[1] - t["line"]) <= WINDOW)


def score_fixture(truth, rows, not_run=frozenset(), commits=None):
    """truth: set1 rows for ONE fixture; rows: parse_rows output. commits: {path: introducing sha}. -> dict."""
    commits = commits or {}
    rows = [r for r in rows if r[2] not in not_run]
    pos = [t for t in truth if t["kind"] == "positive"]
    hits = [t for t in pos if any(matches(r, t, commits.get(t["file"])) for r in rows)]
    fps = [t for t in truth if t["kind"] == "decoy" and any(matches(r, t, commits.get(t["file"])) for r in rows)]
    return {"positives": len(pos), "hits": len(hits), "fp_decoy": [[t["file"], t["line"]] for t in fps],
            "missed": [[t["file"], t["line"]] for t in pos if t not in hits]}


def score_control(rows, not_run=frozenset()):
    """Control fixture: every row from an IaC/CI/secrets tool is a FP."""
    return sorted({(r[0], r[1]) for r in rows if r[2] not in not_run and r[2].startswith(IAC_TOOLS)})


def summarize(per_fx, control_fp):
    pos = sum(v["positives"] for v in per_fx.values())
    hits = sum(v["hits"] for v in per_fx.values())
    fp = sum(len(v["fp_decoy"]) for v in per_fx.values()) + len(control_fp)
    recall = hits / pos if pos else 0.0
    prec = hits / (hits + fp) if hits + fp else 1.0
    return {"positives": pos, "hits": hits, "fp": fp, "recall": recall, "recall_wilson95_lower": wilson_lower(hits, pos),
            "precision": prec, "precision_wilson95_lower": wilson_lower(hits, hits + fp),
            "pass": recall >= 0.80 and prec >= 0.80}


def sh(cmd, cwd=None):
    """-> (stdout, stderr, status): status is the exit code, or "timeout" (stdout/stderr empty)."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return "", "", "timeout"
    return p.stdout, p.stderr, p.returncode


def run(out, detector, sset="set1"):
    os.makedirs(out)  # refuses to overwrite an earlier run
    with tempfile.TemporaryDirectory() as tmp:
        target, tf = os.path.join(tmp, sset), os.path.join(tmp, "truth.json")
        _, e, st = sh([sys.executable, os.path.join(HERE, sset, "build.py"), target, "--truth", tf])
        if st != 0:
            sys.exit("build.py failed (%s): %s" % (st, e.strip()[-500:]))
        truth = json.load(open(tf))
        per_fx, control_fp, timeouts = {}, [], []
        for fx in sorted({t["fixture"] for t in truth} | {CONTROL}):
            repo = os.path.join(target, fx)
            o, e, st = sh(["bash", os.path.join(detector, RC), "--repo", repo, "--full"], repo)
            if st == "timeout":
                timeouts.append(fx)
            open(os.path.join(out, fx + ".json"), "w").write(o)
            open(os.path.join(out, fx + ".stderr"), "w").write(e)
            rows, nr = parse_rows(o), parse_not_run(e)
            if fx == CONTROL:
                control_fp = score_control(rows, nr)
                continue
            ts = [t for t in truth if t["fixture"] == fx]
            commits = {t["file"]: sh(["git", "-C", repo, "log", "--diff-filter=A", "--format=%H", "--", t["file"]])[0].split()[:1]
                       for t in ts if t.get("history")}
            per_fx[fx] = score_fixture(ts, rows, nr, {k: v[0] for k, v in commits.items() if v})
    res = dict(summarize(per_fx, control_fp), fixtures=per_fx, control_fp=control_fp, timeouts=timeouts)
    json.dump(res, open(os.path.join(out, "score.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ("fixtures", "control_fp")}))
    return res["pass"]


if __name__ == "__main__":
    a = sys.argv[1:]
    opt = lambda f, d: a[a.index(f) + 1] if f in a else d
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    det = os.path.abspath(opt("--detector", os.path.join(HERE, "..", "..", "..")))
    sys.exit(0 if run(opt("--out", os.path.join(HERE, "results-" + stamp)), det, opt("--set", "set1")) else 1)
