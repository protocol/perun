#!/usr/bin/env bash
# Table check behind the bandit/ruff-security twin collapse in review_checks.sh: every number that ruff ships as Snnn and bandit ships as Bnnn must name the
# same check. Names are compared by shared words; the pairs below share none but were read side by side and mean the same (md5/hash, ciphers, urlopen, telnet,
# cElementTree, ftp, xmlrpc). Any other pair without a shared word fails, so a ruff or bandit release that reuses a number for another check is caught here and
# must be excluded from the collapse. Needs both tools; SKIP (exit 0) when either is missing.
set -euo pipefail
command -v ruff >/dev/null && command -v bandit >/dev/null || { echo "SKIP  ruff or bandit not installed"; exit 0; }
python3 - <<'PY'
import json, re, subprocess, sys
d = json.loads(subprocess.run(["ruff", "rule", "--all", "--output-format", "json"], capture_output=True, text=True, check=True).stdout)
S = {r["code"][1:]: r["name"] for r in d if (r.get("code") or "").startswith("S") and r["code"][1:].isdigit()}
B = {k[1:]: v for k, v in re.findall(r"^\s+(B\d{3})\s+(\S+)", subprocess.run(["bandit", "--help"], capture_output=True, text=True).stdout, re.M)}
G = {"suspicious", "usage", "use", "used", "import", "call", "calls", "function", "functions", "with", "no", "in", "a", "of", "the", "any", "other", "test", "tests"}
VETTED = {"303", "304", "310", "312", "313", "321", "411"}
tok = lambda s: {t for t in re.split(r"[-_]", s.lower()) if t not in G}
both = sorted(set(S) & set(B))
bad = [(n, S[n], B[n]) for n in both if n not in VETTED and not tok(S[n]) & tok(B[n])]
for n, s, b in bad: print(f"FAIL  S{n} {s} vs B{n} {b}: meanings differ, exclude from the collapse")
if not both or len(both) < 50: print(f"FAIL  only {len(both)} shared numbers"); sys.exit(1)
if bad: sys.exit(1)
print(f"PASS  {len(both)} shared B/S numbers map to the same check")
print("Tests: 1/1")
PY
