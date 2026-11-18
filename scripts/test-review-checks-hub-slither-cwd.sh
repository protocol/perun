#!/usr/bin/env bash
# review_checks.sh runs slither with its process working directory outside the scanned repository. crytic-compile, even with
# --compile-force-framework solc, walks up from that directory to a foundry.toml and runs the solc binary the config names, so a
# repository could otherwise pick the binary a default review executes. Hermetic part (stub slither that applies the same lookup):
# the cwd is outside the repo, the target is absolute, --solc-working-dir names the repo root, a uri relative to the temp dir maps
# back to the changed file, rows for an imported file are dropped, a uri outside the repo is "not run", and a temp dir inside the
# repo, or a crytic-compile framework marker in any ancestor of the temp dir, is NOT CHECKED. Live part (only when a real slither
# is installed; stub forge and solc, no network): a foundry.toml with solc = "./evil" makes slither run ./evil from the repo root
# (positive control), and the hub run never does. The live part skips where slither is not installed, as on CI.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
REAL_SLITHER=$(command -v slither || true)
T=$(mktemp -d "${TMPDIR:-/tmp}/hubslcwd.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_PWNED="$T/pwned" HUB_LOG="$T/hub.log" EVIL_RAN="$T/evil-ran" SOLC_LOG="$T/solc.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" HOME="$T/home"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" "$T/home" "$T/live" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
R=$(pwd -P)
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir -p contracts; printf 'pragma solidity ^0.8.0;\n' >contracts/Base.sol # unchanged: only imported
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
printf 'pragma solidity ^0.8.0;\nimport "./Base.sol";\n' >contracts/T.sol
# the attack: a foundry.toml naming a repo binary as the compiler
printf '[profile.default]\nsolc = "./evil"\noffline = true\n' >foundry.toml
printf '#!/bin/sh\ntouch "$EVIL_RAN"\necho "Version: 0.8.20+commit.a1b79de6"\n' >evil; chmod +x evil
G add . && G commit -q -m code
# slither stub: logs its physical cwd and argv, applies crytic-compile's walk-up from the process cwd (a foundry.toml found = the
# repo's solc would run), and writes SARIF whose uris are relative to that cwd, as crytic-compile's filename_relative is
cat >"$T/bin/slither" <<'S'
#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
with open(os.environ["HUB_LOG"], "a") as fh:
    fh.write(f"cwd={os.getcwd()}\nslither {' '.join(a)}\n")
d = os.getcwd()
while True:
    if os.path.isfile(os.path.join(d, "foundry.toml")):
        open(os.environ["HUB_PWNED"], "w").close()
        break
    if d == os.path.dirname(d):
        break
    d = os.path.dirname(d)
t = a[0]
rows = [(os.path.relpath(t), 4, "reentrancy-eth"), (os.path.relpath(os.path.join(os.path.dirname(t), "Base.sol")), 9, "base-only")]
if os.environ.get("SL_OUTSIDE"):
    rows = [("/elsewhere/X.sol", 2, "outside")]
res = [{"ruleId": r, "message": {"text": "m"}, "locations": [{"physicalLocation": {"artifactLocation": {"uri": u}, "region": {"startLine": n}}}]} for u, n, r in rows]
with open(a[a.index("--sarif") + 1], "w") as fh:
    json.dump({"version": "2.1.0", "runs": [{"results": res}]}, fh)
sys.exit(255)
S
printf '#!/bin/sh\nexit 0\n' >"$T/bin/solc"; chmod +x "$T/bin/slither" "$T/bin/solc"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep seq; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
run() { PATH="$1:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg f "$1" --arg r "$2" --argjson l "$3" 'any(.[]; .tool=="slither" and .file==$f and .rule==$r and .line==$l)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\bslither\b" "$T/err"; }

: >"$HUB_LOG"; run "$T/bin" || true
cwd=$(sed -n 's/^cwd=//p' "$HUB_LOG")
[ -n "$cwd" ] && case "$cwd/" in "$R"/*) false ;; esac && [ ! -e "$HUB_PWNED" ] && [ ! -e "$EVIL_RAN" ] \
  && ok "slither runs from a directory outside the repo: the repo's foundry.toml is never found" || bad "cwd=$cwd pwned=$([ -e "$HUB_PWNED" ] && echo yes || echo no)"
grep -qF -- "slither $R/contracts/T.sol --sarif " "$HUB_LOG" && grep -qF -- "--solc-working-dir $R" "$HUB_LOG" \
  && ok "argv: absolute target, --solc-working-dir is the repo root (solc still resolves imports there)" || bad "argv: $(grep '^slither' "$HUB_LOG")"
ran && row contracts/T.sol reentrancy-eth 4 && ok "a uri relative to the temp dir maps back to the changed file" || bad "rows: $(jq -c '[.[]|select(.tool=="slither")]' "$T/out")"
! jq -e 'any(.[]; .tool=="slither" and .rule=="base-only")' "$T/out" >/dev/null && ok "a row for an imported file is not pinned on the changed file" || bad "import row: $(jq -c '[.[]|select(.tool=="slither")]' "$T/out")"
SL_OUTSIDE=1 run "$T/bin" || true
grep -q 'not run: slither (contracts/T.sol: 1 row(s) with a path outside the repository' "$T/err" && ! ran && ok "a uri outside the repo: not run, never clean" || bad "outside: $(grep slither "$T/err")"
mkdir "$R/tmpin"; : >"$HUB_LOG"; TMPDIR="$R/tmpin" run "$T/bin" || true
grep -q 'NOT CHECKED: slither (the temp dir is inside the repository' "$T/err" && [ ! -s "$HUB_LOG" ] && ok "a temp dir inside the repo: NOT CHECKED, slither never run" || bad "tmp in repo: $(grep slither "$T/err")"
rm -r -- "$R/tmpin"
# a marker in an ancestor of the temp dir (outside the repo, e.g. a shared /tmp): crytic-compile would build with that framework
for mk in foundry.toml hardhat.config.js Makefile; do
  mkdir -p "$T/anc-$mk/tmp"; printf 'all:\n\tdapp build\n' >"$T/anc-$mk/$mk"; : >"$HUB_LOG"; TMPDIR="$T/anc-$mk/tmp" run "$T/bin" || true
  grep -q "NOT CHECKED: slither (a crytic-compile framework marker (.*) is in an ancestor of the temp dir" "$T/err" && [ ! -s "$HUB_LOG" ] \
    && ok "a $mk in an ancestor of the temp dir: NOT CHECKED, slither never run" || bad "ancestor $mk: $(grep slither "$T/err")"
done

# live probe: the real slither and crytic-compile, a stub forge that answers as forge would for this foundry.toml, a stub PATH solc
if [ -z "$REAL_SLITHER" ]; then echo "skip - live probe: slither not installed"; else
  ln -s "$REAL_SLITHER" "$T/live/slither"
  printf '#!/bin/sh\necho %s\n' "'{\"solc\":\"./evil\",\"offline\":true}'" >"$T/live/forge"
  printf '#!/bin/sh\necho "solc $*" >>"$SOLC_LOG"\n[ "$1" != --version ] || { echo "Version: 0.8.20+commit.a1b79de6"; exit 0; }\nexit 1\n' >"$T/live/solc"
  chmod +x "$T/live/forge" "$T/live/solc"; printf '{}\n' >"$T/empty.json"
  # positive control: run from the repo root (the old shape), slither must run ./evil, else this host's crytic-compile differs and the probe proves nothing
  (cd "$R" && PATH="$T/live:$T/sys" "$T/live/slither" contracts/T.sol --compile-force-framework solc --config-file "$T/empty.json" --sarif "$T/ctl.sarif" >/dev/null 2>&1) || true
  if [ ! -e "$EVIL_RAN" ]; then echo "skip - live probe: run from the repo root, this slither never reached ./evil"; else
    rm -f "$EVIL_RAN" "$SOLC_LOG"; run "$T/live" || true
    [ ! -e "$EVIL_RAN" ] && grep -q '^solc --version' "$SOLC_LOG" 2>/dev/null \
      && ok "live: the hub's slither compiles with the PATH solc and never runs the repo's ./evil" || bad "live: evil=$([ -e "$EVIL_RAN" ] && echo ran || echo no) solc=$(head -3 "$SOLC_LOG" 2>/dev/null | tr '\n' ' ')"
  fi
fi
[ "$fail" = 0 ]
