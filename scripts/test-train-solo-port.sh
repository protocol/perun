#!/usr/bin/env bash
# Tests for (1) the per-stage free port stage_run.py gives every train-* stage (TRAIN_PORT / PORT, no fixed-port EADDRINUSE) and
# (2) the flaky re-ride escape: a train ended by flaky-only reds is ledgered "flaky", and a PR that rode TRAIN_SOLO_AFTER of them lands
# alone (train_yield.py solo) instead of riding another union. Every runner is a stub; gh is a PATH stub. Writes only under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-train-solo-port.XXXXXX")"
trap '[ -n "$WORK" ] && rm -r "$WORK" 2>/dev/null' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PERUN_HEAVY_DIR="$WORK/hv/heavy" PERUN_TRAIN_LEDGER="$WORK/ledger.jsonl" WORK SC
unset TRAIN_PORT PORT TRAIN_SOLO_AFTER
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
stage() { python3 "$SC/stage_run.py" "$@"; }

# stage_env with a stand-in socket (the sandbox may forbid real local binds): a train-* stage gets TRAIN_PORT, PORT mirrors it only when unset,
# a caller-set TRAIN_PORT is kept, a non-train stage gets no port, and a bind failure fails open (no port, the stage still runs).
python3 - "$SC" <<'PY'
import os, socket, sys
sys.path.insert(0, sys.argv[1]); import stage_run as sr
class S:
    port = 4321
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def bind(self, a): S.port += 1; self.p = S.port
    def getsockname(self): return ("127.0.0.1", self.p)
real = socket.socket; socket.socket = S
for k in ("TRAIN_PORT", "PORT"): os.environ.pop(k, None)
a, b = sr.stage_env("train-browser"), sr.stage_env("train-rerun")
assert a["TRAIN_PORT"] != b["TRAIN_PORT"] and a["PORT"] == a["TRAIN_PORT"], (a.get("TRAIN_PORT"), b.get("TRAIN_PORT"))
assert sr.stage_env("pregate") is None
os.environ.update(TRAIN_PORT="4444", PORT="5555")
c = sr.stage_env("train-x"); assert (c["TRAIN_PORT"], c["PORT"]) == ("4444", "5555")
os.environ.pop("TRAIN_PORT"); os.environ.pop("PORT")
import contextlib, io
def warned(env):  # stderr of one stage_env call under `env`
    for k in ("TRAIN_PORT", "PORT"): os.environ.pop(k, None)
    os.environ.update(env); err = io.StringIO()
    with contextlib.redirect_stderr(err): sr.stage_env("train-x")
    return err.getvalue()
w = warned({"PORT": "5555"})
assert w.count("\n") == 1 and "PORT=5555" in w and "differs from TRAIN_PORT" in w, w
assert warned({}) == "" and warned({"TRAIN_PORT": "4444", "PORT": "4444"}) == "" and warned({"TRAIN_PORT": "4444"}) == ""
assert warned({"TRAIN_PORT": "4444", "PORT": "5555"}).count("\n") == 1
for k in ("TRAIN_PORT", "PORT"): os.environ.pop(k, None)
def boom(*a): raise PermissionError(1, "Operation not permitted")
S.bind = boom; d = sr.stage_env("train-x"); assert "TRAIN_PORT" not in d and "PORT" not in d
PY
ok $? "stage_env: own port per train-* stage, caller values kept, one warning for a caller PORT that differs from TRAIN_PORT, non-train stage untouched, bind failure fails open"
d=$(stage --name pregate -- bash -c 'echo "[${TRAIN_PORT:-}][${PORT:-}]"')
[ "$d" = "[][]" ]; ok $? "a non-train stage runs with no port"
if python3 -c 'import socket; socket.socket().bind(("127.0.0.1", 0))' 2>/dev/null; then  # real binds allowed: end to end
  a=$(stage --name train-browser -- bash -c 'echo $TRAIN_PORT $PORT'); b=$(stage --name train-browser -- bash -c 'echo $TRAIN_PORT $PORT')
  read -r a1 a2 <<<"$a"; read -r b1 b2 <<<"$b"
  [[ $a1 =~ ^[0-9]+$ ]] && [ "$a1" = "$a2" ] && [ "$a1" != "$b1" ]; ok $? "real run: each train-* stage gets its own TRAIN_PORT"
  stage --name train-browser -- python3 -c 'import os, socket; socket.socket().bind(("127.0.0.1", int(os.environ["TRAIN_PORT"])))'
  ok $? "real run: the handed-out port is bindable"
else
  [ -z "${CI:-}" ]; ok $? "CI must allow real local binds (the real-bind port tests above only run when it does)"
  e=$(stage --name train-browser -- bash -c 'echo "[${TRAIN_PORT:-}]"' 2>/dev/null); [ "$e" = "[]" ]; ok $? "binds forbidden here: the stage still runs, TRAIN_PORT unset"
fi

# --- flaky re-ride escape ---------------------------------------------------------------------------------------------------------
R="$WORK/clone"; g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git init -q --bare "$WORK/origin.git" -b main; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g commit -q --allow-empty -m base; g push -q origin HEAD:main; B=$(g rev-parse HEAD)
for n in 1 2 3; do g checkout -q -b "pr$n" "$B"; echo "$n" >"$R/f$n"; g add "f$n"; g commit -q -m "pr $n"; g push -q origin "pr$n:refs/pull/$n/head"; done
g checkout -q --detach "$B"; for n in 1 2 3; do g merge -q --no-ff -m "merge-train: #$n" "pr$n"; done; U123=$(g rev-parse HEAD)
export B U123 H1=$(g rev-parse pr1) H2=$(g rev-parse pr2) H3=$(g rev-parse pr3)
mkdir -p "$WORK/bin"; cat >"$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
case "$1 $2" in
  "pr view") case "$5" in headRefOid) v=H$3; echo "${!v}" ;; baseRefName) echo main ;; isDraft) echo false ;;
                mergeable) echo MERGEABLE ;; headRefName) echo br$3 ;;
                headRefOid,statusCheckRollup) v=H$3  # checks: $WORK/roll<N> when present, else one passed check
                  printf '{"headRefOid":"%s","statusCheckRollup":%s}\n' "${!v}" "$(cat "$WORK/roll$3" 2>/dev/null || echo '[{"__typename":"CheckRun","status":"COMPLETED","conclusion":"SUCCESS"}]')" ;; esac ;;
  "pr diff") echo changelog.d/x.md ;;
  "pr merge") echo "merged $3" >>"$WORK/merged.log"; echo "$3 $6" >>"$WORK/pinned.log"  # N and the --match-head-commit sha
              { [ -e "$WORK/hv/heavy.exclusive" ] && echo held || echo free; } >>"$WORK/lease.log" ;;  # was the exclusive heavy lease held at the merge?
esac
STUB
chmod +x "$WORK/bin/gh"; export PATH="$WORK/bin:$PATH"
echo 'echo ran >>"$WORK/verified"; echo "GREEN base=$B union=$U123"' >"$WORK/verify.sh"
echo 'if [ "$UNION_SHA" = "$U123" ]; then echo "FAIL t1"; echo "FAILURES 1"; exit 1; fi; exit 0' >"$WORK/browser.sh"
# rerun.sh: t1 fails 2 of 3 solo runs at the union (a flake) and never on the base (an intermittent regression: CANT).
cat >"$WORK/rerun.sh" <<'STUB'
f=$WORK/useq; [ -e f1 ] || f=$WORK/bseq
r=$(head -c1 "$f"); tail -c +2 "$f" >"$f.n"; mv "$f.n" "$f"; [ "$r" != F ] || { echo "FAIL $TEST"; exit 1; }
STUB
# rerun2.sh: t1 fails every solo run at the union (all three PR files present) and passes with any one PR alone: a REAL failure no PR is pinned for.
echo '{ [ -e f1 ] && [ -e f2 ] && [ -e f3 ]; } && { echo "FAIL $TEST"; exit 1; }; exit 0' >"$WORK/rerun2.sh"
cd "$R" || exit 2
run() { # run <tag> <pr>...: one train over a red browser stage ($RR picks the rerun stub)
  local t=$1; shift; : >"$WORK/merged.log"; : >"$WORK/pinned.log"; : >"$WORK/lease.log"; : >"$WORK/verified"; printf FFP >"$WORK/useq"; printf PPPP >"$WORK/bseq"
  VERIFY_CMD="bash $WORK/verify.sh \"\$@\"" UNION_DIRS="$R" LOG_DIR="$WORK" BROWSER_CMD="bash $WORK/browser.sh" RERUN_CMD="bash $WORK/${RR:-rerun.sh}" FLAKE_RUNS=3 \
    bash "$SC/train_land.sh" "$t" "$@" 2>&1
}
last() { tail -1 "$WORK/ledger.jsonl" | python3 -c "import json,sys; print(json.load(sys.stdin)$1)"; }
HEADS3="1:$H1 2:$H2 3:$H3"
seed() { rm -f "$WORK/ledger.jsonl"; for i in 1 2 3; do python3 "$SC/train_yield.py" record "s$i" "$1" "" "${OC:-flaky}" "${2-}"; done; }  # seed <prs> [heads]: 3 flaky rides

out=$(run t1 1 2 3); rc=$?
[ $rc -eq 3 ] && grep -q '^CANT: flake t1 never fails on the base' <<<"$out" && [ "$(last '["outcome"]')" = "" ] && [ "$(last '["heads"]["2"]')" = "$H2" ]
ok $? "the intermittent-regression CANT is not ledgered flaky; the ride records each PR's head sha"
out=$(RR=rerun2.sh TRAIN_SPLIT_DEPTH=0 run t2 1 2 3); rc=$?
[ $rc -eq 3 ] && grep -q 'CANT: no culprit pinned for the real failures' <<<"$out" && [ "$(last '["outcome"]')" = unpinned ]
ok $? "no culprit (every PR passes the failing ids alone) is ledgered unpinned"

# Three no-culprit rides at the same head (real trains) -> the 4th train lands exactly one PR alone; the others stay in that train.
rm -f "$WORK/ledger.jsonl"; for i in 1 2 3; do RR=rerun2.sh TRAIN_SPLIT_DEPTH=0 run "r$i" 1 2 3 >/dev/null; done
out=$(RR=rerun2.sh TRAIN_SPLIT_DEPTH=0 run r4 1 2 3)
[ "$(grep -c 'landing alone' <<<"$out")" = 1 ] && grep -q '^train_land: #1 rode >= 3 trains' <<<"$out" && [ "$(head -1 "$WORK/pinned.log")" = "1 $H1" ] && [ -s "$WORK/verified" ]
ok $? "3 unpinned rides at the same head give exactly one solo landing, merge pinned to that head; the rest still get a union gate"
# An intermittent-regression CANT is never counted, however often it repeats.
rm -f "$WORK/ledger.jsonl"; for i in 1 2 3; do run i$i 1 2 3 >/dev/null; done; out=$(run i4 1 2 3)
! grep -q 'landing alone' <<<"$out" && [ ! -s "$WORK/merged.log" ] && ! grep -q '"outcome": "\(flaky\|unpinned\)"' "$WORK/ledger.jsonl"
ok $? "3 intermittent-regression rides at the same head are never counted toward solo"

rm -f "$WORK/ledger.jsonl"; for i in 1 2; do python3 "$SC/train_yield.py" record "s$i" "1 2 3" "" flaky "$HEADS3"; done; out=$(run t3 1 2 3)
! grep -q 'landing alone' <<<"$out" && [ ! -s "$WORK/merged.log" ]; ok $? "two flaky rides (under TRAIN_SOLO_AFTER=3) still ride the union"
OC=unpinned seed "1 2 3" "$HEADS3"; out=$(run t4 1 2 3); rc=$?
[ "$(grep -c 'landing alone' <<<"$out")" = 1 ] && grep -q '^train_land: #1 rode >= 3 trains' <<<"$out" && [ "$(head -1 "$WORK/pinned.log")" = "1 $H1" ] && [ -s "$WORK/verified" ]
ok $? "with three eligible PRs only the first lands alone; the others stay in the train (re-tested on the new base)"
[ "$(head -1 "$WORK/lease.log")" = free ]; ok $? "the exclusive heavy lease is released before the solo land"

seed "1" "1:$H1"; out=$(run t5 1 2 3); rc=$?
grep -q 'landing alone' <<<"$out" && [ "$(head -1 "$WORK/merged.log")" = "merged 1" ] && [ -s "$WORK/verified" ]
ok $? "only the PR that rode 3 flaky trains lands alone; the rest of the train still gets its union gate (rc=$rc)"
seed "1" "1:$H1"; out=$(run t6 1 2); rc=$?
grep -q '1 PR(s) left (not landed): #2' <<<"$out" && [ "$(cat "$WORK/merged.log")" = "merged 1" ] && [ ! -s "$WORK/verified" ] && [ $rc -eq 0 ]
ok $? "one PR left after the solo landing is reported as left (not landed), not silently skipped"

for roll in '[{"__typename":"CheckRun","status":"COMPLETED","conclusion":"FAILURE"}]' '[{"__typename":"CheckRun","status":"IN_PROGRESS","conclusion":""}]' '[]' \
            '[{"__typename":"StatusContext","state":"FAILURE"}]'; do
  echo "$roll" >"$WORK/roll1"; seed "1" "1:$H1"; out=$(run t7 1 2 3)
  grep -q '#1 rode >= 3 flaky-only or unpinned trains but its head has no all-green checks' <<<"$out" && ! grep -q 'merged 1' "$WORK/merged.log" && [ -s "$WORK/verified" ]
  ok $? "solo candidate with checks $roll is not landed alone and stays in the train"
done; rm -f "$WORK/roll1"
seed "1" "1:deadbeef"; out=$(run t8 1 2 3)
! grep -q 'landing alone' <<<"$out" && [ ! -s "$WORK/merged.log" ]; ok $? "head drift: rides recorded at an older head do not count toward solo"
seed "1"; out=$(run t9 1 2 3)
! grep -q 'landing alone' <<<"$out" && [ ! -s "$WORK/merged.log" ]; ok $? "rides with no recorded head never count toward solo"
seed "1" "1:$H1"; out=$(TRAIN_SOLO_AFTER=0 run t10 1 2 3)
! grep -q 'landing alone' <<<"$out" && [ ! -s "$WORK/merged.log" ]; ok $? "TRAIN_SOLO_AFTER=0 turns the escape off"

: >"$WORK/merged.log"; out=$(LAND_PRS="1:deadbeef" bash "$SC/land_train.sh" "$B" - 2>&1)
grep -q '^SKIP #1 moved' <<<"$out" && [ ! -s "$WORK/merged.log" ]; ok $? "land_train LAND_PRS=<n>:<sha> skips a PR whose head is not the pinned sha"

rm -f "$WORK/ledger.jsonl"; python3 "$SC/train_yield.py" record u1 "1 2" "" flaky "1:$H1 2:$H2"; python3 "$SC/train_yield.py" record u2 "1 2" "" flaky "1:$H1 2:old"
python3 "$SC/train_yield.py" record u3 "1 2" "" flaky "1:$H1 2:$H2"; python3 "$SC/train_yield.py" record u4 "1" "1" "" "1:$H1"
for oc in unpinned flaky ""; do python3 "$SC/train_yield.py" record "v$oc" "3" "" "$oc" "3:$H3"; done  # PR 3: unpinned + flaky count, an outcome-less ride does not
python3 - <<PY
import sys; sys.path.insert(0, "$SC")
import train_yield as ty
p = "$WORK/ledger.jsonl"
assert ty.solo(p, {"1": "$H1", "2": "$H2"}, 3) == [], "PR 1 landed; PR 2 has only 2 rides at its head"
assert ty.solo(p, {"2": "$H2"}, 2) == ["2"] and ty.solo(p, {"2": "old"}, 2) == [], "only rides at the current head count"
assert ty.solo(p, {"2": ""}, 1) == [] and ty.solo(p, {"2": "$H2"}, 0) == []
assert ty.solo(p, {"3": "$H3"}, 2) == ["3"] and ty.solo(p, {"3": "$H3"}, 3) == [], "unpinned and flaky rides count, outcome-less ones do not"
assert ty.solo("$WORK/missing.jsonl", {"1": "$H1"}, 1) == []
assert ty.parse_heads(["1:abc", "2", "x:y:z"]) == {"1": "abc", "2": "", "x": "y:z"}
PY
ok $? "train_yield.solo: current-head rides only, skips a landed PR, an empty head, a missing ledger and 0 (off)"

echo "Tests: $pass/$((pass + fail))"
[ "$fail" -eq 0 ]
