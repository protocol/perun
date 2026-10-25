#!/usr/bin/env python3
"""Tests the gitleaks half of the privacy gate: scripts/secret_scan.py and its wiring in scripts/ci-gates.sh.

Fake tokens are assembled from fragments so this file never trips the gate. Offline; temp dirs only.
"""
import pathlib, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOKEN = "gh" "p_" + "Mq7Zt2Vb9Nx4Lk8RcD3HfJw5Rs1Yp6GuAe3B"


def gate(d):
    r = subprocess.run(["bash", str(ROOT / "scripts/ci-gates.sh"), "privacy", "--banlist", str(d / ".banlist.txt"), str(d)],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


with tempfile.TemporaryDirectory() as t:
    d = pathlib.Path(t)
    (d / ".banlist.txt").write_text("nevermatch-zzz\n")
    (d / "ok.txt").write_text("GITHUB_TOKEN=" + "gh" "p_" + "x" * 36 + "\n")
    rc, out = gate(d)
    assert rc == 0, out
    (d / "leak.txt").write_text("GITHUB_TOKEN=" + TOKEN + "\n")
    rc, out = gate(d)
    assert rc != 0 and "gitleaks rule matched" in out and "leak.txt" in out and TOKEN not in out, out
    (d / "bin.dat").write_bytes(b"\0" + TOKEN.encode())
    (d / "leak.txt").unlink()
    assert gate(d)[0] == 0  # binary files skipped like grep -I

# the allow list is exact repo-relative path plus unchanged sha256
LEAKS = "docs/bench/security-gates-1024/secret-leaks.txt"
ent = [l.split(None, 1) for l in (ROOT / "scripts/secret-scan-allow.txt").read_text().splitlines() if l and not l.startswith("#")]
assert ent and not any("*" in e[1] for e in ent), ent
assert any(e[1] == LEAKS for e in ent)


def scan(f):
    return subprocess.run([sys.executable, "-I", str(ROOT / "scripts/secret_scan.py"), str(f)], capture_output=True, text=True).returncode


assert scan(ROOT / LEAKS) == 0  # the real pinned file is skipped
with tempfile.TemporaryDirectory() as t:
    t = pathlib.Path(t)
    subprocess.run(["git", "-C", str(t), "init", "-q"], check=True)
    p = t / LEAKS; p.parent.mkdir(parents=True); p.write_bytes((ROOT / LEAKS).read_bytes())
    assert scan(p) == 0  # same path, same bytes: skipped
    p.write_text(p.read_text() + "x\n")
    assert scan(p) == 1  # same path, edited: scanned
    other = t / "other" / LEAKS; other.parent.mkdir(parents=True); other.write_bytes((ROOT / LEAKS).read_bytes())
    assert scan(other) == 1  # same bytes under a longer path: scanned (no suffix match)

# a pinned frozen corpus is skipped by the gate only while its bytes match the pin: an appended real-format key fails privacy
with tempfile.TemporaryDirectory() as t:
    t = pathlib.Path(t)
    subprocess.run(["git", "-C", str(t), "init", "-q"], check=True)
    c = t / "docs/bench/security-gates-heldout2-1024/secret-leaks.txt"; c.parent.mkdir(parents=True)
    c.write_bytes((ROOT / "docs/bench/security-gates-heldout2-1024/secret-leaks.txt").read_bytes())
    (t / ".banlist.txt").write_text("nevermatch-zzz\n")
    assert gate(t)[0] == 0, "unmodified pinned corpus must be skipped"
    c.write_text(c.read_text() + "GITHUB_TOKEN=" + TOKEN + "\n")
    rc, out = gate(t)
    assert rc != 0 and "secret-leaks.txt" in out, out

# a 40k-char line must not make the gitleaks regexes quadratic
import time
t0 = time.time()
with tempfile.TemporaryDirectory() as t:
    f = pathlib.Path(t) / "long.txt"; f.write_text("cohere_api_key = " + "a" * 40000 + "\n")
    assert scan(f) in (0, 1)
assert time.time() - t0 < 5, time.time() - t0
print("secret scan union: ok")
