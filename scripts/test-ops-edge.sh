#!/usr/bin/env bash
# Regression tests for ops-script edge cases: clean_finished (spaces in paths, missing lsof, archive name
# collision), land_train (failed merge exits non-zero), prefile_check (invalid banlist regex fails closed),
# pipe_mask_guard (test-runner pipes).
# Plain bash; prints PASS/FAIL lines and "N passed, M failed"; exits non-zero on any failure. Writes only under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(cd "$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-ops.XXXXXX")" && pwd -P)"
trap 'rm -rf "$WORK"' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
R="$WORK/clone"
g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git init -q --bare "$WORK/origin.git" -b main; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g commit -q --allow-empty -m base; g push -q origin HEAD:main; B=$(g rev-parse HEAD)

# --- clean_finished: gh stub reports every PR MERGED at the branch head ---
mkdir -p "$WORK/bin" "$WORK/wts"
cat >"$WORK/bin/gh" <<'EOF'
#!/usr/bin/env bash
wt=$(git worktree list --porcelain | awk -v b="refs/heads/$3" '/^worktree /{w=substr($0,10)} $0 == "branch " b {print w}')
echo "MERGED $(git -C "$wt" rev-parse HEAD)"
EOF
chmod +x "$WORK/bin/gh"
mkdir -p "$WORK/wts/sp ace"
g worktree add -q -b sp "$WORK/wts/sp ace/w s" "$B"
out=$(cd "$R" && ROOT="$WORK/wts" GH="$WORK/bin/gh" ARCHIVE_DIR="$WORK/ar" bash "$SC/clean_finished.sh" 2>&1)
[ ! -d "$WORK/wts/sp ace/w s" ] && grep -q "removed=1" <<<"$out"; ok $? "clean_finished: a worktree path with spaces is removed"

mkdir -p "$WORK/wts/x" "$WORK/wts/y"
g worktree add -q -b cx "$WORK/wts/x/same" "$B"; g worktree add -q -b cy "$WORK/wts/y/same" "$B"
echo one >"$WORK/wts/x/same/a"; echo two >"$WORK/wts/y/same/b"
git -C "$WORK/wts/x/same" add a; git -C "$WORK/wts/y/same" add b
(cd "$R" && ROOT="$WORK/wts" GH="$WORK/bin/gh" ARCHIVE_DIR="$WORK/ar" bash "$SC/clean_finished.sh" >/dev/null 2>&1)
grep -qs '^+one' "$WORK"/ar/*.patch && grep -qs '^+two' "$WORK"/ar/*.patch; ok $? "clean_finished: same-named dirty worktrees keep separate archives"

g worktree add -q -b lz "$WORK/wts/lz" "$B"
mkdir -p "$WORK/nolsof"
for t in git awk grep head cat mkdir basename rm ps bash env dirname sed cut tr sort; do ln -sf "$(command -v $t)" "$WORK/nolsof/$t"; done
(cd "$R" && ROOT="$WORK/wts" GH="$WORK/bin/gh" PATH="$WORK/nolsof" bash "$SC/clean_finished.sh" >/dev/null 2>&1); rc=$?
[ $rc -eq 2 ] && [ -d "$WORK/wts/lz" ]; ok $? "clean_finished: missing lsof fails closed (exit 2, nothing removed)"
g worktree remove --force "$WORK/wts/lz"

# --- land_train: a failing merge command must not exit 0 ---
for n in 1 2; do g checkout -q -b "pr$n" "$B"; echo "$n" >"$R/f$n"; g add "f$n"; g commit -q -m "pr $n"; done
g checkout -q --detach "$B"
for n in 1 2; do g merge -q --no-ff -m "merge-train: #$n" "pr$n"; done
U=$(g rev-parse HEAD)
cat >"$WORK/bin/gh2" <<EOF
#!/usr/bin/env bash
cd "$R"
case "\$1 \$2" in
 "pr view") case "\$7" in .headRefOid) git rev-parse pr\$3;; .baseRefName) echo main;; .isDraft) echo false;; .mergeable) echo MERGEABLE;; .headRefName) echo pr\$3;; esac;;
 "pr diff") echo changelog.d/x.md;;
esac
EOF
chmod +x "$WORK/bin/gh2"
out=$(cd "$R" && UNION_DIRS="$R" GH="$WORK/bin/gh2" LAND_CMD='echo nope; exit 1' bash "$SC/land_train.sh" "$B" "$U" 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "FAILED rc=1: nope" <<<"$out"; ok $? "land_train: failing merge command exits 1 and prints FAILED"
(cd "$R" && UNION_DIRS="$R" GH="$WORK/bin/gh2" LAND_CMD='echo merged' bash "$SC/land_train.sh" "$B" "$U" >/dev/null 2>&1); ok $? "land_train: all merges succeed -> exit 0"

# --- prefile_check: an invalid banlist regex refuses instead of passing silently ---
PF="$ROOT/.claude/skills/contribution/scripts/prefile_check.sh"
mkdir "$WORK/pf"; printf '[unclosed\n' >"$WORK/pf/.banlist.txt"; printf 'title' >"$WORK/pf/t"; printf 'plain body' >"$WORK/pf/b"
BANLIST_DIR="$WORK/pf" bash "$PF" "$WORK/pf/t" "$WORK/pf/b" >/dev/null 2>&1; [ $? -eq 1 ]; ok $? "prefile_check: invalid banlist regex fails closed"
printf 'AKIA[0-9A-Z]{16}\n' >"$WORK/pf/.banlist.txt"
BANLIST_DIR="$WORK/pf" bash "$PF" "$WORK/pf/t" "$WORK/pf/b" >/dev/null 2>&1; ok $? "prefile_check: valid banlist and clean text passes"

# --- pipe_mask_guard: test-runner pipes and |& are flagged ---
pmg() { printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "$1" | python3 "$SC/pipe_mask_guard.py" | grep -q additionalContext; }
pmg 'pytest -q | tail' && pmg 'make ci |& tail' && pmg 'pnpm run lint | head' && pmg 'npm test 2>&1 | tee out.log' && ! pmg 'ls | grep foo' && ! pmg 'set -o pipefail; pytest | tail'  # bash4-ok: quoted fixture text, not shell syntax
ok $? "pipe_mask_guard: pytest/make/lint/tee pipes flagged; ls|grep and pipefail pass"


printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
