#!/usr/bin/env bash
# install.sh hygiene: --dry-run writes nothing, the end-of-install summary splits vendored from generated files,
# and machine-local state (.perun/, the uninstall record, settings backups) lands in .git/info/exclude, once.
# Runs only against throwaway git repos under $TMPDIR with HOME, CLAUDE_CONFIG_DIR and XDG_CACHE_HOME redirected.
# Prints PASS/FAIL per case and a final "Tests: P/N"; exits non-zero on any failure.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-inst-hyg.XXXXXX")"
trap 'find "$WORK" -depth -delete' EXIT
export HOME="$WORK/home" CLAUDE_CONFIG_DIR="$WORK/home/.claude" XDG_CACHE_HOME="$WORK/cache" TMPDIR="$WORK"
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
mkdir -p "$HOME"
SH=bash; [ -x /bin/bash ] && SH=/bin/bash   # macOS /bin/bash is 3.2: the portability target
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
snap() { (cd "$1" && find . -path ./.git -prune -o -print | LC_ALL=C sort); }

T="$WORK/tgt"; mkdir -p "$T/.claude"; git -C "$T" init -q
echo '{}' > "$T/.claude/settings.local.json"   # an existing file makes the operating-layer merge write a .bak
before="$(snap "$T")"; ex_before="$(cat "$T/.git/info/exclude")"

h0="$(snap "$HOME")"
dry="$("$SH" "$ROOT/install.sh" --dry-run --with-delivery "$T" 2>/dev/null)"; rc=$?
[ "$rc" -eq 0 ]; ok $? "--dry-run exits 0"
[ "$(snap "$T")" = "$before" ] && [ "$(cat "$T/.git/info/exclude")" = "$ex_before" ]; ok $? "--dry-run leaves the target (files and .git/info/exclude) untouched"
[ "$(snap "$HOME")" = "$h0" ]; ok $? "--dry-run writes nothing under HOME (the sandbox probe is skipped)"
grep -q '^DRY RUN: nothing was written' <<<"$dry" && grep -q '^Vendored' <<<"$dry" && grep -q '^Generated' <<<"$dry" \
  && grep -q '\.claude/skills/deep-code-review/ (' <<<"$dry" && grep -q '\.claude/\.perun-install\.json' <<<"$dry"; ok $? "--dry-run lists vendored and generated files"
[ -z "$(find "$WORK" -maxdepth 1 -name 'perun-dry.*' -o -maxdepth 1 -name 'perun-stamp.*')" ]; ok $? "--dry-run removes its scratch dir"

out="$(DCR_NO_PROBE=1 "$SH" "$ROOT/install.sh" --with-delivery "$T" 2>/dev/null)"; rc=$?
[ "$rc" -eq 0 ]; ok $? "real install exits 0"
v="$(sed -n '/^Vendored/,/^Generated/p' <<<"$out")"; g="$(sed -n '/^Generated/,$p' <<<"$out")"
grep -q 'skills/deep-code-review/ (' <<<"$v" && ! grep -q 'AGENTS.md' <<<"$v" && grep -q 'AGENTS.md' <<<"$g" \
  && grep -q '\.claude/commands/review\.md' <<<"$g"; ok $? "install summary splits vendored from generated"
st="$(git -C "$T" status --porcelain -uall)"
! grep -qE '\.perun|\.bak' <<<"$st" && ls "$T"/.claude/settings.local.json.bak.* >/dev/null 2>&1; ok $? "backup, uninstall record and .perun/ are written but not untracked in git status"
DCR_NO_PROBE=1 "$SH" "$ROOT/install.sh" --with-delivery "$T" >/dev/null 2>&1
n="$(grep -cxF '/.perun/' "$T/.git/info/exclude")"
[ "$n" -eq 1 ]; ok $? "re-install does not duplicate exclude entries (got $n)"
echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
