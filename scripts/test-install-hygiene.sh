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

# The summary names only what this run wrote: files other processes write under a host dir during the install (a home target's
# .claude/ holds session transcripts and todos) never appear, and every file the run did write still does. The 2099 mtimes are newer
# than the install's own stamp; zz-other.txt is a generic stray in every host dir, .perun, .githooks, scripts and .github/workflows, so a scan root covering a whole
# dir would list it. PERUN_ROLE is unset so the policy and settings rows always appear.
T2="$WORK/tgt2"; mkdir -p "$T2/.claude/projects" "$T2/.claude/todos"; git -C "$T2" init -q
echo '{}' > "$T2/.claude/projects/p.jsonl"; echo '[]' > "$T2/.claude/todos/t.json"
touch -t 209901010000 "$T2/.claude/projects/p.jsonl" "$T2/.claude/todos/t.json"
for d in .claude .cursor .agents .codex .gemini .opencode .github .windsurf .hermes .kiro .cline .roo .factory .qwen .grok .perun .githooks scripts .github/workflows; do
  mkdir -p "$T2/$d"; echo x > "$T2/$d/zz-other.txt"; touch -t 209901010000 "$T2/$d/zz-other.txt"
done
out2="$(env -u PERUN_ROLE DCR_NO_PROBE=1 "$SH" "$ROOT/install.sh" --full --with-gates --with-terse-replies --with-extra-hosts --with-codex "$T2" 2>/dev/null)"
! grep -qE 'projects/p\.jsonl|todos/t\.json' <<<"$out2"; ok $? "summary omits other processes' files under .claude/"
! grep -q 'zz-other' <<<"$out2"; ok $? "summary omits a stray file in every host dir, .perun, .githooks, scripts and .github/workflows"
miss="$(cd "$T2" && find . -path ./.git -prune -o -type f ! -path '*/skills/*/*' ! -path './.claude/projects/*' ! -path './.claude/todos/*' ! -name zz-other.txt -print \
  | sed 's|^\./||' | while IFS= read -r f; do grep -qxF -e "  $f" <<<"$out2" || echo "$f"; done)"
[ -z "$miss" ] && grep -q '^  AGENTS\.md$' <<<"$out2" && grep -q '^  \.perun/policy\.json$' <<<"$out2" && grep -q '^  \.claude/settings\.local\.json$' <<<"$out2"
ok $? "summary still lists every file the run wrote (missing: ${miss:-none})"
rows="$(sed -nE 's|^  (\.claude/skills/[^/]+/) \([1-9][0-9]* files\)$|\1|p' <<<"$out2" | LC_ALL=C sort)"
[ "$rows" = "$(cd "$T2" && ls -d .claude/skills/*/ | LC_ALL=C sort)" ] && grep -q '^\.claude/skills/deep-code-review/$' <<<"$rows"
ok $? "summary has one (N files) row per installed skill dir, deep-code-review included"

# An existing target: edited gate files and a settings.local.json make install write .new and .bak siblings, and a stale .new puts the
# operating-layer snippet at .new-1. Each sibling glob in the summary's scan roots must list its file, so dropping a trailing * fails.
rowmiss() { local f; for f in "${@:2}"; do grep -qxF -e "  $f" <<<"$1" || printf '%s ' "$f"; done; }   # summary rows of $1 that are absent
T3="$WORK/tgt3"; mkdir -p "$T3/.github/workflows" "$T3/scripts" "$T3/.githooks" "$T3/.claude"; git -C "$T3" init -q
for f in .github/workflows/dcr-gates.yml scripts/dcr-gates.sh scripts/integrator-gate.sh .githooks/pre-push; do echo '# local edit' > "$T3/$f"; done
echo '{}' > "$T3/.claude/settings.local.json"; echo '{}' > "$T3/.claude/settings.operating-layer.json.new"
out3="$(env -u PERUN_ROLE DCR_NO_PROBE=1 "$SH" "$ROOT/install.sh" --with-delivery --with-gates "$T3" 2>/dev/null)"
m="$(rowmiss "$out3" .github/workflows/dcr-gates.yml.new scripts/dcr-gates.sh.new scripts/integrator-gate.sh.new .githooks/pre-push.new)"
[ -z "$m" ] && grep -qE '^  \.claude/settings\.local\.json\.bak\.[0-9]{8}-[0-9]{6}(-[0-9]+)?$' <<<"$out3"
ok $? "summary lists the gate-file .new siblings and the settings.local.json .bak (missing: ${m:-none})"
out4="$(env -u PERUN_ROLE DCR_NO_PROBE=1 "$SH" "$ROOT/install.sh" --with-delivery --with-operating-layer --no-sandbox "$T3" 2>/dev/null)"
m="$(rowmiss "$out4" .claude/settings.operating-layer.json.new-1 .claude/.dcr-install-flags.local)"
[ -z "$m" ] && ! grep -qxF '  .claude/settings.operating-layer.json.new' <<<"$out4"
ok $? "summary lists the operating-layer .new-1 and the local flags file, not the stale .new (missing: ${m:-none})"
echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
