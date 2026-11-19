#!/usr/bin/env python3
"""Tests: audit_sweep v9. The scanner env drops GH_TOKEN, GITHUB_TOKEN, the --token-env variable, REVIEW_TEST_CMD, REVIEW_FUZZ and
REVIEW_SCORECARD (other variables pass through); an empty repo is skipped without an ERROR row (a plain directory still errors); two
same-named repos (two local paths, or two orgs) keep separate state and each reports its own findings; a repo's rows reach stdout before save() records them as seen (a block-buffered stdout is flushed
first); the hub's "set REVIEW_TEST_CMD to run it" rows (repo-local tsc, eslint-security, psalm, ansible-lint, checkov, tflint) are
non-blocking ENV gaps whose texts match review_checks.sh. AUDIT_SWEEP_PY=<path> tests another copy (used to prove the cases fail
before the change). No network; temp dirs are removed."""
import contextlib, importlib.util, io, os, subprocess, sys, tempfile

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts")
S = os.environ.get("AUDIT_SWEEP_PY") or os.path.join(D, "audit_sweep.py")
sys.path.insert(0, D)
spec = importlib.util.spec_from_file_location("audit_sweep", S)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
ok = 0


def check(c, msg):
    global ok
    if not c:
        sys.exit(f"FAIL: {msg}")
    ok += 1


def repo(t):
    p = os.path.join(t, "acme")
    os.makedirs(p)
    subprocess.run(["git", "-C", p, "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", p, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", "commit", "-q", "--allow-empty", "-m", "a"],
                   check=True, capture_output=True)
    return p


def test_scanner_env_scrubbed(t):
    p, dump = repo(t), os.path.join(t, "env.txt")
    wrap = os.path.join(t, "checks.sh")
    with open(wrap, "w") as fh:
        fh.write(f'env > "{dump}"; echo "[]"\n')
    scrub = ("GH_TOKEN", "GITHUB_TOKEN", "MYTOK", "REVIEW_TEST_CMD", "REVIEW_FUZZ", "REVIEW_SCORECARD")
    env = dict(os.environ, AUDIT_SWEEP_CHECKS=wrap, KEEPME="1", **{k: "x" for k in scrub})
    r = subprocess.run([sys.executable, S, "--local", p, "--state", os.path.join(t, "s.json"), "--token-env", "MYTOK"],
                       capture_output=True, text=True, env=env)
    check(r.returncode == 0, f"sweep exit {r.returncode}: {r.stdout} {r.stderr}")
    with open(dump) as fh:
        names = {line.split("=", 1)[0] for line in fh}
    check("KEEPME" in names, "other variables reach the scanner")
    check(not names & set(scrub), f"scrubbed variables reached the scanner: {sorted(names & set(scrub))}")


def test_rows_flushed_before_save(t):
    p, buf = repo(t), io.BytesIO()
    seen_at_save = []
    real_sweep, real_save, real_argv = a.sweep_repo, a.save, sys.argv

    def sweep(name, path, st):
        st["seen"] = ["f" * 64]
        return [(name, "first", "k.env", "exposed-secret", "secret-exposure", "f" * 12)]

    def save(state, path):
        seen_at_save.append(buf.getvalue())
        return 0
    out = io.TextIOWrapper(buf, encoding="utf-8")  # block-buffered: nothing reaches buf until a flush
    a.sweep_repo, a.save, sys.argv = sweep, save, ["audit_sweep.py", "--local", p, "--state", os.path.join(t, "s.json")]
    try:
        with contextlib.redirect_stdout(out):
            rc = a.main()
    finally:
        a.sweep_repo, a.save, sys.argv = real_sweep, real_save, real_argv
    check(rc == 0 and seen_at_save, f"main ran and saved: rc={rc}")
    check(b"f" * 12 in seen_at_save[0], f"row on stdout before the first save: {seen_at_save[0]!r}")
    out.detach()


def test_project_code_rows_are_env_gaps(t):
    with open(os.path.join(D, "review_checks.sh")) as fh:
        hub = fh.read()
    pcode = "it executes project code (its config and plugins); set REVIEW_TEST_CMD to run it"
    rows = {"eslint-security": pcode, "psalm": pcode, "ansible-lint": pcode,
            "tsc": "repo-local tsc not run (set REVIEW_TEST_CMD to run it: it executes project code)",
            "checkov": "a .checkov.yaml or .checkov.yml in the repo root can load Python checks (external-checks-dir); set REVIEW_TEST_CMD to run it",
            "tflint": "infra/main.tf: a .tflint.hcl, .tflint.json or .tflint.d beside it can load plugin binaries; set REVIEW_TEST_CMD to run it"}
    for tool, text in rows.items():
        check((text.split(": ", 1)[1] if tool == "tflint" else text) in hub, f"{tool} text not in review_checks.sh (drift)")
        x = {"tool": tool, "rule": "not-checked", "file": "", "message": text}
        check(a.env_gap(x) and not a.not_installed(x), f"{tool} project-code row is an ENV gap")
        check(not a.env_gap(dict(x, tool="devskim")), f"{tool} text under another tool stays blocking")
    check(a.env_gap({"tool": "tflint", "rule": "not-checked", "file": "", "message": rows["tflint"].replace("infra/main.tf", "a b/c.tf")}),
          "tflint row for a path with a space")
    check(not a.env_gap({"tool": "tflint", "rule": "not-checked", "file": "", "message": rows["tflint"].split(": ", 1)[1]}),
          "tflint row needs its file prefix")


def test_permanent_rows_are_env_gaps(t):
    with open(os.path.join(D, "review_checks.sh")) as fh:
        hub = fh.read()
    # (tool, row text, the parts review_checks.sh holds verbatim when the text embeds a path): layout and provisioning rows no rescan closes
    ks = ("no local nsa.json and cis-v1.23-t1.0.1.json in ", " (kubescape download artifacts; never fetched)")
    rows = [("eslint-security", "the eslint config names no security plugin", ()), ("kubescape", "Helm chart templates are not rendered by the hub", ()),
            ("psalm", "no psalm.xml at repo root", ()), ("gosec", "no go.mod at repo root", ()), ("govulncheck", "no go.mod at repo root", ()),
            ("staticcheck", "no go.mod at repo root", ()), ("govulncheck", "go toolchain missing", ()), ("staticcheck", "go toolchain missing", ()),
            ("retire", "REVIEW_RETIRE_JSREPO names no local jsrepository.json (never fetched)", ()), ("cargo-deny", "cargo toolchain missing", ()),
            ("kubescape", ks[0] + "/home/jane/.kubescape" + ks[1], ks), ("kubescape", ks[0] + "~/.kubescape" + ks[1], ks),
            ("cargo-audit", "no local advisory DB at ~/.cargo/advisory-db (never fetched)", ("no local advisory DB at ", "/advisory-db (never fetched)"))]
    for tool, text, parts in rows:
        check(all(s in hub for s in parts or (text,)), f"{tool} {text!r} not in review_checks.sh (drift)")
        x = {"tool": tool, "rule": "not-checked", "file": "", "message": text}
        check(a.env_gap(x) and not a.not_installed(x), f"{tool} {text!r} is an ENV gap")
        check(not a.env_gap(dict(x, file="a.go")) and not a.env_gap(dict(x, tool="devskim")), f"{tool} {text!r} needs its tool and an empty file")
    check(not a.env_gap({"tool": "cargo-audit", "rule": "not-checked", "file": "", "message": "no local advisory DB at  (never fetched)"}),
          "cargo-audit row needs a path")


def test_periodic_full(t):
    p, log = repo(t), os.path.join(t, "log")
    wrap = os.path.join(t, "checks.sh")
    with open(wrap, "w") as fh:
        fh.write(f'echo "$*" >> "{log}"; echo "[]"\n')
    real = a.CHECKS
    a.CHECKS = wrap

    def scans():
        try:
            with open(log) as fh:
                return fh.read().splitlines()
        except FileNotFoundError:
            return []
    try:
        st = {}
        a.sweep_repo("acme", p, st)
        check(len(scans()) == 1 and "--full" in scans()[0] and st.get("full", 0) > 0, f"first run is --full and stamps it: {scans()} {st}")
        a.sweep_repo("acme", p, st)
        check(len(scans()) == 1, "an idle repo inside FULL_EVERY is skipped")
        st["full"] -= a.FULL_EVERY
        old = st["full"]
        a.sweep_repo("acme", p, st)
        check(len(scans()) == 2 and "--full" in scans()[1] and st["full"] > old, f"an idle repo past FULL_EVERY rescans --full: {scans()}")
        st.pop("full")
        a.sweep_repo("acme", p, st)
        check(len(scans()) == 3 and "--full" in scans()[2] and "full" in st, "a state written before `full` existed rescans once")
    finally:
        a.CHECKS = real


def test_empty_repo_skipped(t):
    wrap, log = os.path.join(t, "checks.sh"), os.path.join(t, "log")
    with open(wrap, "w") as fh:
        fh.write(f'echo "$*" >> "{log}"; exit 1\n')
    env = dict(os.environ, AUDIT_SWEEP_CHECKS=wrap, GIT_CEILING_DIRECTORIES=t)
    empty, plain = os.path.join(t, "empty"), os.path.join(t, "plain")
    os.makedirs(plain)
    subprocess.run(["git", "init", "-q", empty], check=True, capture_output=True)
    sweep = lambda p: subprocess.run([sys.executable, S, "--local", p, "--state", os.path.join(t, "s.json")], capture_output=True, text=True, env=env)
    r = sweep(empty)
    check(r.returncode == 0 and r.stdout.count("\n") == 1 and not os.path.exists(log), f"empty repo: no scan, header only, exit 0: {r.returncode} {r.stdout!r}")
    r = sweep(plain)
    check(r.returncode == 1 and "\tERROR\t" in r.stdout, f"a directory that is not a repo still errors: {r.returncode} {r.stdout!r}")


def test_same_name_repos_apart(t):
    wrap = os.path.join(t, "checks.sh")
    with open(wrap, "w") as fh:
        fh.write('echo \'[{"file": "f.py", "line": 1, "rule": "r", "text": "x", "tool": "fake"}]\'\n')
    state, paths = os.path.join(t, "s.json"), []
    for d in ("one", "two"):
        p = os.path.join(t, d, "acme")
        os.makedirs(p)
        subprocess.run(["git", "-C", p, "init", "-q"], check=True, capture_output=True)
        subprocess.run(["git", "-C", p, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", "commit", "-q", "--allow-empty", "-m", d],
                       check=True, capture_output=True)
        paths.append(p)
    env = dict(os.environ, AUDIT_SWEEP_CHECKS=wrap)
    rows = lambda p: [l.split("\t") for l in subprocess.run([sys.executable, S, "--local", p, "--state", state], capture_output=True, text=True,
                                                             env=env).stdout.splitlines()[1:] if "\tCOVERAGE\t" not in l]  # host-dependent CORE row
    first = [rows(p) for p in paths]
    check(all(len(x) == 1 and x[0][1] == "first" and x[0][3] == "r" for x in first), f"each same-named local repo reports its own finding: {first}")
    check(first[0][0][0] != first[1][0][0] and first[0][0][5] != first[1][0][5], f"repo column and fingerprint differ: {first}")
    check(rows(paths[0]) == [], "the first repo's state was not clobbered by the second")
    real_list, real_argv, real_checks = a.list_repos, sys.argv, a.CHECKS
    a.list_repos, a.CHECKS, out = (lambda org, tok: [("acme", paths[0])]), wrap, io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            for org in ("o1", "o2"):
                sys.argv = ["audit_sweep.py", "--org", org, "--token-env", "NOPE", "--state", os.path.join(t, "org.json")]
                check(a.main() == 0, f"--org {org} swept")
    finally:
        a.list_repos, sys.argv, a.CHECKS = real_list, real_argv, real_checks
    got = [l.split("\t")[:2] for l in out.getvalue().splitlines() if not l.startswith("repo\t") and "\tCOVERAGE\t" not in l]
    check(got == [["o1/acme", "first"], ["o2/acme", "first"]], f"two orgs with one repo name keep separate state: {got}")


for f in (test_scanner_env_scrubbed, test_rows_flushed_before_save, test_project_code_rows_are_env_gaps, test_permanent_rows_are_env_gaps,
          test_periodic_full, test_empty_repo_skipped, test_same_name_repos_apart):
    with tempfile.TemporaryDirectory() as t:
        f(t)
print(f"Tests: {ok}/{ok}")
