#!/usr/bin/env bash
# Tests: bypass_guard.py, _dirty_guard.sh, merge_checkpoint.sh, session_brief merge line, owner-gated banners,
# and the CI lint that every skill script running git checkout/switch/reset uses the dirty-tree guard.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-pp4.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then pass=$((pass+1)); echo "PASS $2"; else fail=$((fail+1)); echo "FAIL $2"; fi; }
bg() { python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]}}))' "$1" >"$WORK/in.json"
  python3 "$SC/bypass_guard.py" <"$WORK/in.json" 2>/dev/null; }
deny() { bg "$1"; [ $? -eq 2 ]; ok $? "bypass_guard denies: $1"; }
allow() { bg "$1"; [ $? -eq 0 ]; ok $? "bypass_guard allows: $1"; }
deny 'git commit --no-verify -m x'
deny 'git commit -n -m x'
deny 'git commit -anm x'
deny 'git push --no-verify origin main'
deny 'git merge --no-verify topic'
deny 'HUSKY=0 git commit -m x'
deny 'SKIP=lint git push'
deny 'export HUSKY=0; git commit -m x'
deny 'git -c core.hooksPath=/dev/null commit -m x'
deny 'cd d && git commit -m x --no-verify'
allow 'git commit -m "mention --no-verify and -n in text"'
allow 'git commit -m note'
allow 'git commit -mnote'
allow 'git push -n origin main'
allow 'git merge -n topic'
allow 'HUSKY=0 npm test'
allow 'git status'
echo '{bad' | python3 "$SC/bypass_guard.py"; ok $? "bypass_guard: bad stdin exits 0"
python3 -c 'import json,sys
t=json.load(open(sys.argv[1]))
assert any("bypass_guard.py" in h["command"] for e in t["hooks"]["PreToolUse"] for h in e["hooks"])' "$ROOT/.claude/skills/agentic-delivery/templates/operating-layer.settings.json"
ok $? "template wires bypass_guard.py"

# dirty guard
. "$SC/_dirty_guard.sh"
R="$WORK/r"; mkdir "$R"; git -C "$R" init -q; git -C "$R" config user.email t@example.com; git -C "$R" config user.name T
echo a >"$R/f"; git -C "$R" add f; git -C "$R" commit -qm i
require_clean_tree "$R"; ok $? "dirty guard: clean tree passes"
echo b >"$R/f"
err=$(require_clean_tree "$R" 2>&1); rc=$?
[ "$rc" -ne 0 ] && grep -q "commit or stash" <<<"$err" && grep -q "throwaway worktree" <<<"$err"; ok $? "dirty guard: dirty tree refused with exact fix"
git -C "$R" checkout -q -- f
echo c >"$R/f"
out=$(cd "$R" && GH=true UNION_DIRS="$R" VERIFY_CMD=true bash "$SC/train_land.sh" t 1 2 2>&1); rc=$?
[ "$rc" -eq 2 ] && grep -q "uncommitted changes" <<<"$out" && grep -q "park for the owner" <<<"$out"; ok $? "train_land: banner then refuses dirty tree (exit 2)"
out=$(UNION_DIRS="$R" bash "$SC/land_train.sh" a b 2>&1); grep -q "park for the owner; do not retry or route around" <<<"$out"; ok $? "land_train: owner-gated banner"
git -C "$R" checkout -q -- f

# merge checkpoint
git -C "$R" checkout -qb topic; echo t >"$R/f"; git -C "$R" commit -qam t
git -C "$R" checkout -q -; echo m >"$R/f"; git -C "$R" commit -qam m
git -C "$R" merge topic >/dev/null 2>&1
[ -z "$(cd "$R" && bash "$SC/merge_checkpoint.sh" status)" ]; ok $? "checkpoint: status silent without state"
(cd "$R" && bash "$SC/merge_checkpoint.sh" save >/dev/null); ok $? "checkpoint: save during conflicted merge"
st=$(cd "$R" && bash "$SC/merge_checkpoint.sh" status)
grep -q "unresolved \[f\]" <<<"$st"; ok $? "checkpoint: conflicted file listed unresolved"
echo done >"$R/f"; (cd "$R" && bash "$SC/merge_checkpoint.sh" save >/dev/null)
st=$(cd "$R" && bash "$SC/merge_checkpoint.sh" status)
grep -q "resolved \[f\]" <<<"$st" && grep -q "git commit" <<<"$st"; ok $? "checkpoint: resolved-unstaged file and next command"
bl=$(cd "$R" && python3 -c "import sys;sys.path.insert(0,'$SC');import session_brief as b,pathlib;print(b.merge_line(pathlib.Path('.')))")
grep -q "resume merge" <<<"$bl"; ok $? "session_brief shows the merge checkpoint"
git -C "$R" merge --abort; (cd "$R" && bash "$SC/merge_checkpoint.sh" save 2>/dev/null); [ $? -eq 2 ]; ok $? "checkpoint: save refuses with no merge"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
