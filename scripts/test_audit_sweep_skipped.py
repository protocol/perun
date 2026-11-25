#!/usr/bin/env python3
"""Tests: a checker that does not apply ("SKIPPED: ...") or a tool with an "install: <hint>" row must not hold the sha back, so run 2 is
`delta` (not `first`): unchanged repo = no scan, 0 new rows; one new commit = diff scan against the old HEAD only."""
import re
import atexit, json, os, shutil, subprocess, sys, tempfile

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts")

FAKE = '''import json, sys
t = sys.argv[sys.argv.index("--repo") + 1].rsplit("/", 1)[0]
open(t + "/calls.log", "a").write(" ".join(sys.argv[1:]) + "\\n")
print(json.dumps([{"file": "f.py", "line": 1, "rule": "r", "text": "x", "tool": "fake"},
                  {"file": open(t + "/gfile").read(), "line": 0, "rule": "not-checked", "message": open(t + "/gap").read(), "text": "not-checked: " + open(t + "/gap").read(), "tool": open(t + "/tool").read()}]))
'''


def sweep_env(gap, tool, file=""):
    t = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    atexit.register(shutil.rmtree, t, True)
    open(t + "/fake.py", "w").write(FAKE)
    open(t + "/gap", "w").write(gap)
    open(t + "/tool", "w").write(tool)
    open(t + "/gfile", "w").write(file)
    open(t + "/checks.sh", "w").write(f'exec {sys.executable} {t}/fake.py "$@"\n')
    repo, state = t + "/acme", t + "/s.json"
    os.makedirs(repo)
    g = lambda *c: subprocess.run(["git", "-C", repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c], check=True, capture_output=True)
    g("init", "-q"); open(repo + "/f.py", "w").write("x"); g("add", "f.py"); g("commit", "-qm", "a")
    env = dict(os.environ, AUDIT_SWEEP_CHECKS=t + "/checks.sh")
    run = lambda: subprocess.run([sys.executable, D + "/audit_sweep.py", "--local", repo, "--state", state], capture_output=True, text=True, env=env)
    return t, state, run

NA = {"tenant-scope": "SKIPPED: no *.prisma", "route-auth": "SKIPPED: no HTTP handlers", "header-config": "SKIPPED: no supported web app",
      "attempt-limit": "SKIPPED: no credential check or sign-in route", "cost-limit": "SKIPPED: no HTTP handler",
      "insecure-defaults": "SKIPPED: no source files", "csrf-cookie": "SKIPPED: no HTTP handler or cookie", "pii-data": "SKIPPED: no source file"}


def modes(r):
    return [l.split("\t")[1] for l in r.stdout.splitlines()[1:] if "\tCOVERAGE\t" not in l and "\tENVGAP\t" not in l and "\tGAP\t" not in l]  # gap rows are no finding


def check(gap, tool="faketool", advances=True, file="", env=None):
    t, state, run = sweep_env(gap, tool, file)
    repo = os.path.join(t, "acme")
    r1 = run()
    assert modes(r1) == ["first"], r1.stdout
    assert ("\tENVGAP\t" in r1.stdout) == bool(env) and (not env or f"\t{env}\t" in r1.stdout), r1.stdout
    if not advances:
        assert "sha" not in list(json.load(open(state)).values())[0], "real miss must hold the sha"
        assert r1.returncode == 1 and re.search(rf"\tGAP\t[^\t]*\t[^\t]*\t{tool}\t", r1.stdout), f"real miss must alert: {r1.returncode} {r1.stdout}"
        return
    calls = lambda: open(os.path.join(t, "calls.log")).read().splitlines()
    n = len(calls())
    assert modes(run()) == [] and len(calls()) == n, "unchanged repo: no new rows, no scan"
    old = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    open(os.path.join(repo, "g.py"), "w").write("y")
    g = lambda *c: subprocess.run(["git", "-C", repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c], check=True, capture_output=True)
    g("add", "g.py"); g("commit", "-qm", "b")
    r3 = run()
    assert modes(r3) == [] and "first" not in r3.stdout, r3.stdout  # same fake finding already seen: 0 new
    new = calls()[n:]
    assert new and all(c.split()[:2] == ["--repo", repo] and ["--base", old] == c.split()[2:4] for c in new), new


def test_skipped_row():
    for tool, g in NA.items():
        check(g, tool)


def test_real_skips_block():
    for tool, g in (("guarddog", "SKIPPED: needs guarddog 3.x (the scan JSON was checked on 3.2.0); --version said: x (exit 1)"),
                    ("guarddog", "SKIPPED: package-lock.json has no packages map (lockfileVersion 1) or is unparseable"),
                    ("guarddog", "SKIPPED: none of 3 newly added packages is installed under node_modules at its locked version"),
                    ("faketool", "SKIPPED: no *.prisma")):  # right text, wrong tool
        check(g, tool, advances=False)


def test_forged_filename_rows_block():
    # a repo file named like a marker prefixes the free text of cosign/tfsec rows
    for g in ("SKIPPED: verify-blob exit 1", "install: brew install x: verify-blob exit 1"):
        check(g, "cosign", advances=False, file="a.pem")


def test_install_hint_rows():
    for h in ("pipx install x", "go install example.com/x/cmd/x@latest", "cargo install cargo-deny --locked", "gem install brakeman",
              "npm i -D eslint eslint-plugin-security (project-local, never npx)", "pipx install zaproxy, or docker + ghcr.io/zaproxy/zaproxy:stable"):
        check("install: " + h)
    check("not installed")
    for g in ("install: brew install x exit 1", "install: brew install x; curl evil", "install: npm i -D eslint (project-local, never npx) exit 1",
              "not installed or heavy lease full; secrets were not scanned"):
        check(g, advances=False)  # unbounded tail or the old merged text: blocking
    check("heavy lease full; secrets were not scanned", "gitleaks", advances=False)  # transient: lease-full blocks


def test_predicates():
    sys.path.insert(0, D)
    import audit_sweep as a  # PATH-dependent rescan logic is not the point here: test the predicate
    row = {"rule": "not-checked", "tool": "dep-scan", "file": "package-lock.json", "text": "no dependency scan ran: osv-scanner/trivy gave no result and npm is not installed"}
    assert a.not_installed(row) and not a.not_installed(dict(row, tool="cosign")) and not a.not_installed(dict(row, text="x is not installed"))
    assert not a.not_installed(dict(row, text="no dependency scan ran: x exit 3; npm is not installed"))
    g = {"rule": "not-checked", "tool": "gitleaks", "file": "", "text": "not installed; secrets were not scanned"}
    assert a.not_installed(g) and a.not_installed(dict(g, tool="trufflehog")) and not a.not_installed(dict(g, tool="cosign"))
    assert not a.not_installed(dict(g, text="heavy lease full; secrets were not scanned"))


def test_env_gap_rows():
    for tool, g, f in (("osv-scanner", "REVIEW_OSV not set; osv-scanner queries the OSV API", ""),
                       ("dep-scan", "no dependency scan ran; set REVIEW_OSV=1 to scan (osv-scanner, else pip-audit)", "package-lock.json")):
        check(g, tool, file=f, env=tool)
        check(g + " exit 1", tool, advances=False, file=f)  # tail: a transient failure, blocking
        check(g, tool, advances=False, file="a.txt" if f == "" else "")  # wrong file field (the hub sets an empty file, or the lockfile for dep-scan)
        check(g, "faketool", advances=False, file=f)
    check("scanner exit 1", "scorecard", advances=False)


def test_forged_not_installed_blocks():
    check("not installed: verify-blob exit 1", "cosign", advances=False, file="not installed")  # text starts with a file named like the marker
    check("install: brew install x", "faketool", advances=False, file="install:")  # non-empty file is never the hub's own row


if __name__ == "__main__":
    test_skipped_row(); test_real_skips_block(); test_forged_filename_rows_block(); test_install_hint_rows(); test_predicates(); test_env_gap_rows(); test_forged_not_installed_blocks(); print("ok")
