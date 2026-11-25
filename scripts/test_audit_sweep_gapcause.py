#!/usr/bin/env python3
"""Tests: every GAP and ENVGAP row names its cause as counted class labels, never message text: one row of each kind per tool (file = the
first sorted file among that tool's rows of the kind, rule = "<n> not-checked: <class> <k>, ..."); a message holding a fake token, email
and URL never reaches stdout or stderr; the closed class list falls back to "other"; the invisible-chars partial-read row and the
committed-data one-file container and partial-read rows are ENVGAP rows (full match, file required) while the output cap, unreadable,
collapsed containers, per-file containers under 4 files, timeouts and "exit N" rows stay blocking GAP rows. Synthetic data only; no network."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", ".claude", "skills", "deep-code-review", "scripts")
sys.path.insert(0, D)
FAKE = '''import os, sys
a = sys.argv[1:]
t = os.path.dirname(a[a.index("--repo") + 1])
print(open(t + "/rows.json").read())
'''
ok = 0


def check(c, m):
    global ok
    if not c:
        raise AssertionError(m)
    ok += 1


def nc(tool, m, file=""):
    return {"file": file, "line": 0, "rule": "not-checked", "text": "not-checked: " + m, "message": m, "tool": tool}


def sweep(rows):
    """One `audit_sweep.py --local` run on a one-commit repo whose fake scanner prints `rows`. Returns (rc, TSV rows, stdout, stderr, state)."""
    t = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    try:
        for n, body in (("fake.py", FAKE), ("rows.json", json.dumps(rows)), ("checks.sh", f'exec {sys.executable} {t}/fake.py "$@"\n')):
            with open(os.path.join(t, n), "w") as fh:
                fh.write(body)
        repo, state = os.path.join(t, "acme"), os.path.join(t, "s.json")
        os.makedirs(repo)
        for c in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "a"]):
            subprocess.run(["git", "-C", repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c], check=True, capture_output=True)
        env = dict(os.environ, AUDIT_SWEEP_CHECKS=os.path.join(t, "checks.sh"))
        r = subprocess.run([sys.executable, os.path.join(D, "audit_sweep.py"), "--local", repo, "--state", state], capture_output=True, text=True, env=env)
        st = list(json.load(open(state)).values()) if os.path.exists(state) else []
        return r.returncode, [l.split("\t") for l in r.stdout.splitlines()[1:]], r.stdout, r.stderr, (st[0] if st else {})
    finally:
        shutil.rmtree(t, ignore_errors=True)


def kind(rows, k):
    return [x[2:5] for x in rows if x[1] == k]


def test_both_kinds_in_one_repo_each_name_their_cause():
    PART = "partially scanned: file over 2 MB, only the first 2 MB were read"
    rc, rows, _, _, st = sweep([nc("invisible-chars", PART, "z.txt"), nc("invisible-chars", PART, "b.txt"),
                                nc("invisible-chars", "output capped at 200 rows; later findings and files were not scanned", "m.txt"),
                                nc("invisible-chars", "unreadable: Permission denied", "c.txt"),
                                nc("invisible-chars", "unreadable: Permission denied", "d.txt")])
    check(kind(rows, "ENVGAP") == [["b.txt", "2 not-checked: partial-read 2", "invisible-chars"]], f"ENVGAP: {rows}")
    check(kind(rows, "GAP") == [["c.txt", "3 not-checked: output-cap 1, unreadable 2", "invisible-chars"]], f"GAP: {rows}")
    check(rc == 1 and "sha" not in st, f"blocking row holds the sha and exits 1: {rc} {st}")


def test_message_text_never_reaches_output():
    bad = "tok_FAKE0123456789abcdef jane@example.com https://example.com/path?key=1"
    rc, rows, out, err, _ = sweep([nc("faketool", "weird failure " + bad), nc("faketool", bad, "f.txt")])
    check(kind(rows, "GAP") == [["f.txt", "2 not-checked: crash 1, other 1", "faketool"]], f"labels only, sorted: {rows}")
    for s in ("tok_FAKE", "jane@example.com", "example.com/path", "weird failure"):
        check(s not in out and s not in err, f"{s} leaked: {out} {err}")


def test_unmatched_text_is_other_and_every_class_is_reachable():
    import audit_sweep as a
    samples = {"output-cap": "output capped at 200 rows; later findings and files were not scanned",
               "container-collapsed": "5 parquet containers not scanned (first 3: a, b, c): addresses inside their pages may not be seen, so this is not a clean result",
               "container": "compressed/columnar container (gzip): addresses inside its pages may not be seen, so this is not a clean result",
               "partial-read": "partially scanned: file over 2 MB, only the first 2 MB were read", "unreadable": "unreadable: Permission denied",
               "timeout": "timeout 60s", "exit-code": "exit 2", "lease": "heavy lease full", "missing-tool": "not installed",
               "unparseable": "unparseable report", "config-is-code": "x changed in this diff: its config is code, not run",
               "opt-in": "off by default (license: OSI-licensed code only); set REVIEW_CODEQL=1", "not-provisioned": "no go.mod at repo root",
               "lookup-failed": "NOT RUN: registry lookup failed (URLError)", "rule-not-run": "rule r1 did not run (boom); its hits were not checked",
               "crash": "scanner crashed", "other": "tok_FAKE and nothing else",
               # emitter templates (review_checks.sh skip/nc, dependency_currency.py notes) with synthetic values
               "partial-coverage": "3 of 9 rows named a file outside the scanned list; findings may be missing",
               "noise-path": "noise path excluded by REVIEW_NOISE_RE, not scanned", "bad-config": "REVIEW_SEMGREP_CONFIG must be an existing local path",
               "version-unknown": "NOT RUN: version 9.9 matches no acme release cycle", "unsupported-input": "NOT RUN: docker:// action image is not checked here",
               "missing-file": "signed file x.sig is missing"}
    more = {"version-unknown": ["NOT RUN: registry lists no stable release", "NOT RUN: no currency source for this image", "NOT RUN: pinned by digest only; version unknown",
                                "NOT RUN: SHA pin without a `# vX.Y.Z` comment; version unknown"],
            "unsupported-input": ["x.sig: only a .bundle is verified offline (raw signatures and attestations are not)",
                                  "NOT RUN: image reference uses a variable that is not resolved here"],
            "partial-coverage": ["lib/main.tf: 2 row(s) with a path outside the scanned directory; findings may be missing"],
            "not-provisioned": ["x.sig: no cosign.pub beside it or at the repo root"], "lookup-failed": ["NOT RUN: GitHub lookup failed (URLError: x); currency unknown"],
            "opt-in": ["no dependency scan ran; set REVIEW_OSV=1 to scan (osv-scanner, else npm)"], "missing-tool": ["curl is missing", "pipefail_sigpipe.py missing"]}
    check(sorted(samples) == sorted([n for n, _ in a.CAUSES] + ["other"]), f"closed list {[n for n, _ in a.CAUSES]}")
    for n, m in samples.items():
        check(a.cause(m) == n, f"{m!r} -> {a.cause(m)}, want {n}")
    for n, ms in more.items():
        for m in ms:
            check(a.cause(m) == n, f"{m!r} -> {a.cause(m)}, want {n}")


def test_leading_file_name_does_not_pick_the_class():
    """review_checks.sh `$f: ...` rows (file column empty) and a prefix equal to the row's own file: a path like errors/ or timeout/ is no cause."""
    import audit_sweep as a
    for f, m, want in (("errors/x.bundle", "errors/x.bundle: no cosign.pub beside it or at the repo root", "not-provisioned"),
                       ("fail/y.bundle", "fail/y.bundle: signed file fail/y.sig is missing", "missing-file"),
                       ("timeout/main.tf", "timeout/main.tf: a .tflint.hcl, .tflint.json or .tflint.d beside it can load plugin binaries; set REVIEW_TEST_CMD to run it", "config-is-code"),
                       ("errors/main.tf", "errors/main.tf: 2 row(s) with a path outside the scanned directory; findings may be missing", "partial-coverage"),
                       ):
        for rowfile in (f, ""):
            check(a.cause(m, rowfile) == want, f"{m!r} file={rowfile!r} -> {a.cause(m, rowfile)}, want {want}")
    check(a.cause("exit 5/a.txt: no cosign.pub beside it or at the repo root", "exit 5/a.txt") == "not-provisioned", "a prefix equal to the row's file is dropped")
    check(a.cause("errors/x.bundle: no cosign.pub beside it or at the repo root", "other.txt") == "crash", "a prefix that is not the row's file stays in the text")
    check(a.cause("unreadable: Permission denied", "") == "unreadable" and a.cause("unreadable: Permission denied", "a.txt") == "unreadable", "class text keeps its class")
    check(a.cause("partially scanned: file over 2 MB, only the first 2 MB were read", "") == "partial-read", "no colon-prefix strip for class text")


# (tool, message, file, expect): "env" = ENVGAP, exit 0 and sha stored; "gap" = GAP, exit 1, sha held
PART_PD = "partially scanned: file over 33554432 bytes, only the first 33554432 were read"
CONT = "compressed/columnar container (parquet): addresses inside its pages may not be seen, so this is not a clean result"
CASES = [
    ("invisible-chars", "partially scanned: file over 2 MB, only the first 2 MB were read", "a.txt", "env"),
    ("invisible-chars", "partially scanned: file over 2 MB, only the first 2 MB were read", "", "gap"),  # per-file row needs its file
    ("invisible-chars", "output capped at 200 rows; later findings and files were not scanned", "a.txt", "gap"),
    ("invisible-chars", "partially scanned: file over 2 MB, only the first 2 MB were read; timeout 60s", "a.txt", "gap"),
    ("invisible-chars", "timeout 60s", "", "gap"), ("invisible-chars", "exit 2", "", "gap"),
    ("invisible-chars", "unreadable: Permission denied", "a.txt", "gap"),
    ("committed-data", CONT + "; only the first 33554432 bytes were read", "a.parquet", "env"),
    ("committed-data", PART_PD, "a.bin", "env"),
    ("committed-data", CONT, "a.parquet", "gap"),  # 1-3 files of a kind under the cap: not in the ENV list
    ("committed-data", "4 parquet containers not scanned (first 3: a, b, c): addresses inside their pages may not be seen, so this is not a clean result", "a.parquet", "gap"),
    ("committed-data", "unreadable: Permission denied", "a.bin", "gap"), ("committed-data", PART_PD, "", "gap"),
    ("committed-data", "timeout 60s", "", "gap"), ("committed-data", "exit 2", "", "gap"),
    ("committed-data", CONT + "; only the first 33554432 bytes were read; exit 2", "a.parquet", "gap"),
    ("committed-data", PART_PD + "; timeout 60s", "a.bin", "gap"),
]


def test_env_entries_are_full_matches_and_blocking_rows_stay_blocking():
    for tool, m, f, want in CASES:
        rc, rows, _, _, st = sweep([nc(tool, m, f)])
        got = "env" if kind(rows, "ENVGAP") and not kind(rows, "GAP") else "gap" if kind(rows, "GAP") and not kind(rows, "ENVGAP") else rows
        check(got == want and rc == (0 if want == "env" else 1) and bool(st.get("sha")) == (want == "env"), f"{tool} {m!r} file={f!r}: {got} rc={rc} {st}")


bad = 0
for f in (test_both_kinds_in_one_repo_each_name_their_cause, test_message_text_never_reaches_output,
          test_unmatched_text_is_other_and_every_class_is_reachable, test_leading_file_name_does_not_pick_the_class, test_env_entries_are_full_matches_and_blocking_rows_stay_blocking):
    try:
        f()
    except AssertionError as e:
        bad += 1
        print("FAIL", f.__name__, e)
print(f"Tests: {ok}/{ok + bad}")
sys.exit(1 if bad else 0)
