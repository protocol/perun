#!/usr/bin/env python3
"""Tests: org_leak_sweep.py finds a planted fake token (gitleaks rule) and a fake banned term in a local fixture repo's
history, even after both are deleted from HEAD; the TSV carries repo, file, commit and rule but never the token or the term;
a missing banlist fails closed (exit 2); --out inside a git work tree is refused. No network; every value is fictional."""
import csv
import os
import shutil
import subprocess
import sys
import tempfile

S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts", "org_leak_sweep.py")
TOKEN = "ghp_" + "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv1Wx2"  # fake, split so this file holds no whole token
TERM = "zorblax-acme-internal"


def sh(*c, env=None):
    return subprocess.run(c, capture_output=True, text=True, env=env)


def main():
    if not shutil.which("gitleaks"):
        # script fails closed (exit 3, no TSV) before any scan, so banlist rows cannot be produced either
        with tempfile.TemporaryDirectory() as t:
            out = os.path.join(t, "out")
            r = sh(sys.executable, S, "--local", t, "--no-banlist", "--out", out)
            if r.returncode != 3 or os.path.exists(os.path.join(out, "leaks.tsv")):
                sys.exit(f"FAIL: missing gitleaks must exit 3 with no TSV, got {r.returncode}")
        print("SKIP: gitleaks rule check (not installed); fail-closed exit 3 verified\nTests: 1/1")
        return 0
    ok = 0

    def check(cond, msg):
        nonlocal ok
        if not cond:
            sys.exit("FAIL: " + msg)
        ok += 1

    with tempfile.TemporaryDirectory() as t:
        repo, out = os.path.join(t, "acme-repo"), os.path.join(t, "out")
        os.makedirs(repo)
        env = dict(os.environ, GIT_AUTHOR_NAME="Jane Smith", GIT_AUTHOR_EMAIL="jane@example.com",
                   GIT_COMMITTER_NAME="Jane Smith", GIT_COMMITTER_EMAIL="jane@example.com")
        g = ["git", "-C", repo]
        sh(*g, "init", "-q")
        with open(os.path.join(repo, "cfg.txt"), "w") as fh:
            fh.write(f"token = {TOKEN}\nnote: {TERM}\n")
        sh(*g, "add", ".")
        sh(*g, "commit", "-q", "-m", "add", env=env)
        with open(os.path.join(repo, "cfg.txt"), "w") as fh:
            fh.write("clean\n")
        sh(*g, "commit", "-qam", "scrub", env=env)
        for nm, body in (("café.txt", TERM), ('a"b.txt', TERM), ("plain.txt", "++ " + TERM), (TERM + ".txt", TERM)):
            with open(os.path.join(repo, nm), "w") as fh:
                fh.write(body + "\n")
        sh(*g, "add", ".")
        sh(*g, "commit", "-q", "-m", "more", env=env)
        ban = os.path.join(t, "ban.txt")
        with open(ban, "w") as fh:
            fh.write("# fake\nzorblax-acme-[a-z]+\n")
        r = sh(sys.executable, S, "--local", repo, "--banlist", ban, "--out", out)
        check(r.returncode == 1, f"expected exit 1 got {r.returncode} {r.stderr}")
        with open(os.path.join(out, "leaks.tsv")) as fh:
            tsv = fh.read()
        rows = list(csv.reader(tsv.splitlines(), delimiter="\t"))
        hit = {x[1] for x in rows[1:] if x[3] == "banlist:2"}
        check({"café.txt", 'a"b.txt', "plain.txt", "cfg.txt"} <= hit, f"quoted/++ file hits missing: {hit}")
        check("<redacted>" in hit and not any("zorblax" in x[1] for x in rows), "file column must be redacted")
        check(rows[0] == ["repo", "file", "commit", "rule"], "header")
        rules = {x[3] for x in rows[1:]}
        check("banlist:2" in rules, f"banlist hit missing: {rules}")
        check(any(x != "banlist:2" and not x.startswith("ERROR") for x in rules), f"gitleaks hit missing: {rules}")
        check(all(x[0] == "acme-repo" for x in rows[1:]), "repo column")
        check(TOKEN not in tsv and TOKEN[4:20] not in tsv and "zorblax" not in tsv, "secret or term leaked into TSV")
        check(not os.path.exists(os.path.join(out, "mirrors", "acme-repo.git")), "mirror not cleaned")
        r = sh(sys.executable, S, "--local", repo, "--banlist", os.path.join(t, "nope"), "--out", out)
        check(r.returncode == 2, "missing banlist must fail closed")
        r = sh(sys.executable, S, "--local", repo, "--banlist", ban, "--out", os.path.join(repo, "o"))
        check(r.returncode == 2, "--out inside work tree must be refused")
    print(f"Tests: {ok}/{ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
