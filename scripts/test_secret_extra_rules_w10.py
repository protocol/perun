#!/usr/bin/env python3
"""Regression pins for secrets wave 10 (held-out-13 blind): the Fly.io token rule flags fm1_/fm2_/fm1r_ values under any name and passes near-misses;
the banlist US-SSN pattern no longer matches never-issued numbers (area 000/666/9xx, group 00, serial 0000) but still matches real formats. Tokens built at runtime. Offline.
"""
import hashlib, importlib.util, pathlib, re, subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ss", ROOT / "scripts/secret_scan.py")
ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def tok(seed, n, alpha=B64):
    """Deterministic high-entropy string of length n over alpha."""
    return "".join(alpha[b % len(alpha)] for b in hashlib.sha256(seed.encode()).digest() * 8)[:n]


def ids(text):
    return ss.gitleaks_rule(text + "\n", "x.txt", True)


F2, F1 = "fm" "2_", "fm" "1_"
LIVE = ["Fly" "V1 " + F2 + tok("a", 60) + "==", "FLY_API_" "TOKEN=" + F2 + tok("b", 50), "FLY_ACCESS_" "TOKEN=Fly" "V1 " + F1 + tok("c", 80) + "=",
        "token: " + F1 + tok("d", 45), "Fly" "V1 " + F2 + tok("e", 120) + ",fm" "2_" + tok("f", 30), "authorization: Fly" "V1 fm" "1r_" + tok("g", 60), "FLY_fm" "2_" + tok("k", 50)]
DECOY = ["Fly" "V1 " + F2 + "${FLY_TOKEN}", "FLY_fm" "2_${FLY_TOKEN}", "Fly" "V1 " + F2 + "short", "x" + F2 + tok("h", 60), "fm" "3_" + tok("i", 60), F2 + "0" * 60, "Fly" "V1 " + F2 + "<your-token>",
         "FLY_API_" "TOKEN=" + F2 + "example" + tok("j", 50)]
bad = [("miss", t) for t in LIVE if "flyio-token" not in ids(t)] + [("fp", t) for t in DECOY if ids(t)]
assert not bad, bad
ssn = [l for l in (ROOT / ".banlist.txt").read_text().splitlines() if "-[0-9" not in l and "(0[1-9]|[1-9][0-9])-(000" in l]
assert len(ssn) == 1; rx = re.compile(ssn[0])
for n in ("000" "-00-0000", "000" "-12-3456", "666" "-12-3456", "900" "-12-3456", "987" "-65-4321", "123" "-00-4567", "123" "-45-0000", "ssn: 999" "-99-9999"):
    assert not rx.search(n), n
for n in ("ssn: 078" "-05-1120", "123" "-45-6789", "001" "-01-0001", "665" "-99-9999", "667" "-10-2000", "899" "-98-9998"):
    assert rx.search(n), n
print("secret extra rules w10: ok")
