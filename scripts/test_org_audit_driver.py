#!/usr/bin/env python3
"""Tests: org_audit_driver.py against local file:// fixture repos and a stub review_checks.sh. Checks: a good repo is
scanned from a full (unshallowed) clone with --full-history, --full and no --tests, bundled semgrep rules
forced; NOT CHECKED tools are listed; a missing repo and a bad name are FAILED rows with exit 1; a repo-local
.gitleaks.toml/.gitleaksignore and every symlink are gone from the scanned tree and HEAD; a one-commit repo works; a
failing config-strip commit fails closed; a duplicate output name is FAILED; an empty list exits 2; the temp clone is
removed. Also: the REAL review_checks.sh runs end to end on a file:// repo; owner/.github is accepted, owner/.. rejected; a failing review_checks puts its last stderr line in the reason. No network; every name is fictional."""
import glob, os, shutil, subprocess, sys, tempfile

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts", "org_audit_driver.py")
STUB = """#!/usr/bin/env bash
{ echo "$*"; echo "$REVIEW_SEMGREP_CONFIG"; git -C "$2" rev-list --count HEAD; echo "$2"
  ls -A "$2" | grep -c "^.gitleaks"; git -C "$2" ls-tree HEAD --name-only | grep -c "^.gitleaks"
  find "$2" -name .git -prune -o -type l -print | wc -l | tr -d ' '; } >"$STUB_LOG"
echo "NOT CHECKED: gitleaks (install: brew install gitleaks)" >&2
echo '[{"file":"a.txt","line":1,"rule":"r","message":"m","text":"r: m","tool":"t"}]'
"""
N = [0]


def sh(*c, **kw):
    return subprocess.run(c, capture_output=True, text=True, **kw)


def check(ok, msg):
    N[0] += 1
    if not ok:
        sys.exit("FAIL: " + msg)


def drive(t, names, env, tag):
    repos, out = os.path.join(t, f"repos-{tag}.txt"), os.path.join(t, f"out-{tag}")
    open(repos, "w").write(names)
    r = sh(sys.executable, D, "--repos", repos, "--out", out, env=env)
    return r, out, {l.split("\t")[0]: l.split("\t") for l in r.stdout.splitlines()[1:]}


def mk(t, name, commits, link=False):
    src, bare = os.path.join(t, "src-" + name), os.path.join(t, "acme", name + ".git")
    g = ["git", "-c", "user.name=Jane Smith", "-c", "user.email=jane@example.com"]
    sh("git", "init", "-q", src)
    for i in range(commits):
        open(os.path.join(src, "a.txt"), "w").write(str(i))
        open(os.path.join(src, ".gitleaks.toml"), "w").write("[allowlist]\npaths=['a.txt']\n")
        open(os.path.join(src, ".gitleaksignore"), "w").write("x\n")
        if link and not os.path.islink(os.path.join(src, "lnk")):
            os.symlink("/etc/hosts", os.path.join(src, "lnk"))
        sh(*g, "-C", src, "add", "-A"), sh(*g, "-C", src, "commit", "-qm", f"c{i}")
    os.makedirs(os.path.dirname(bare), exist_ok=True)
    sh("git", "clone", "-q", "--bare", src, bare)


def main():
    with tempfile.TemporaryDirectory() as t:
        mk(t, "widgets", 2, link=True)
        mk(t, "solo", 1)
        stub, log = os.path.join(t, "rc.sh"), os.path.join(t, "log")
        open(stub, "w").write(STUB)
        env = dict(os.environ, ORG_AUDIT_BASE_URL="file://" + t, ORG_AUDIT_REVIEW_CHECKS=stub, STUB_LOG=log)
        r, out, rows = drive(t, "# c\nacme/widgets\nacme/missing\nbad name\n", env, "a")
        check(r.returncode == 1, f"exit 1 expected on failed rows, got {r.returncode}: {r.stderr}")
        check(rows["acme/widgets"][1:3] == ["OK", "1"], f"good row: {rows['acme/widgets']}")
        check("gitleaks" in rows["acme/widgets"][3], "NOT CHECKED tool not listed")
        check(rows["acme/missing"][1] == "FAILED" and rows["bad name"][1] == "FAILED", "failed rows missing")
        flags, sg, n, clone, wt, hd, ln = open(log).read().splitlines()
        check("--full-history" in flags and "--tests" not in flags, f"flags: {flags}")
        check("--full --full-history" in flags and "--base" not in flags, "want --full, no --base")
        check(sg.endswith("templates/semgrep-taint"), f"semgrep config not forced: {sg}")
        check(n == "3", f"want 2 history commits + 1 strip commit: {n}")
        check(wt == "0" and hd == "0", f"repo-local gitleaks config still present: tree {wt}, HEAD {hd}")
        check(ln == "0", f"symlink left in scanned tree: {ln}")
        check(not os.path.exists(clone), "temp clone not cleaned")
        check(len(glob.glob(out + "/acme__widgets-*.json")) == 1 and glob.glob(out + "/summary-*.tsv"), "result files")
        # one-commit repo (nothing to unshallow) scans fine
        r, _, rows = drive(t, "acme/solo\n", env, "b")
        check(r.returncode == 0 and rows["acme/solo"][1] == "OK", f"one-commit repo: {r.stdout} {r.stderr}")
        # duplicate output name is FAILED, first still OK
        r, _, _ = drive(t, "acme/solo\nacme/solo\n", env, "c")
        check(r.returncode == 1 and r.stdout.count("collision") == 1, f"collision: {r.stdout}")
        # empty / comment-only list exits 2
        r, _, _ = drive(t, "# nothing\n\n", env, "d")
        check(r.returncode == 2, f"empty list exit {r.returncode}")
        # a failing strip commit fails closed
        wrap = os.path.join(t, "bin")
        os.makedirs(wrap)
        real = shutil.which("git")
        open(os.path.join(wrap, "git"), "w").write(f'#!/bin/sh\ncase " $* " in *" commit "*) exit 1;; esac\nexec {real} "$@"\n')
        os.chmod(os.path.join(wrap, "git"), 0o755)
        r, _, rows = drive(t, "acme/solo\n", dict(env, PATH=wrap + ":" + os.environ["PATH"]), "e")
        check(r.returncode == 1 and rows["acme/solo"][1] == "FAILED" and "commit" in rows["acme/solo"][3], f"strip commit failure: {r.stdout}")
        # real review_checks.sh, no override: scan completes (fails if --base gets the empty-tree hash)
        mk(t, ".github", 1)
        renv = {k: v for k, v in env.items() if k != "ORG_AUDIT_REVIEW_CHECKS"}
        r, _, rows = drive(t, "acme/.github\nacme/..\nacme/.\n", renv, "f")
        check(rows["acme/.github"][1] == "OK", f"real review_checks / dot repo: {r.stdout} {r.stderr}")
        check(rows["acme/.."][1] == "FAILED" and "bad repo name" in rows["acme/.."][3], "owner/.. accepted")
        check(rows["acme/."][1] == "FAILED", "owner/. accepted")
        # a failing review_checks: last non-empty stderr line lands in the reason, tabs/newlines gone, cut at 200
        bad = os.path.join(t, "bad.sh")
        open(bad, "w").write('#!/usr/bin/env bash\necho first >&2\nprintf "boom\\t%0300d\\n\\n" 0 >&2\nexit 3\n')
        r, _, rows = drive(t, "acme/solo\n", dict(env, ORG_AUDIT_REVIEW_CHECKS=bad), "g")
        reason = rows["acme/solo"][3]
        check("(exit 3): boom 000" in reason and "first" not in reason and len(reason) < 260, f"stderr in reason: {reason}")
    print(f"Tests: {N[0]}/{N[0]}")


main()
