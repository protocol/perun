#!/usr/bin/env bash
#
# Contract self-tests for scripts/ci-gates.sh (Deep Code Review CI gates).
#
# Exercises scripts/ci-gates.sh with the subcommands `privacy`, `routing`,
# `version`, and `install`. That production helper exists at the current HEAD,
# so every case is expected to PASS (GREEN) here. The same cases still prove RED
# during TDD: run against a checkout without the helper (or one whose behaviour
# regresses) they FAIL. Real exit codes are always preserved — no `|| true`, no
# always-success fallback, and no pipeline that swallows the exit status of the
# command under test.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATES="$ROOT/scripts/ci-gates.sh"

# Hermetic run root: mktemp -d (never a fixed name under $ROOT), so N copies
# of this suite launched concurrently — same worktree, same host, whatever —
# each get their own directory and never reuse another run's fixtures. Every
# subprocess this script or a case shells out to (dcr-gates.sh, a selftest,
# a git fixture) inherits TMPDIR/HOME pointed at this run's own root and a
# disabled system/global git config, so no shared /tmp scratch file, no
# ambient ~/.gitconfig identity or hook, and no cross-run git-config write
# ever crosses runs. Every fixture below still sets its own repo-local
# user.email/user.name, so disabling the global config changes nothing they
# rely on.
# ${TMPDIR:-/tmp} already ends in / on macOS; strip it (${...%/}) so the
# template below never doubles up -- a later literal path-string match
# against a child process's pwd-normalized output would otherwise see //
# on one side and / on the other and never match.
_tmp_base="${TMPDIR:-/tmp}"
WORK="$(mktemp -d "${_tmp_base%/}/dcr-test-ci-gates.XXXXXX")"
export TMPDIR="$WORK"
export HOME="$WORK/home"
mkdir -p "$HOME"
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null
# Dozens of cases run the shipped gate runner (dcr-gates.sh), and each run used to re-prove the same idempotent gate
# selftests: most of this suite's wall time (docs/bench/pipeline-1016/). Stamps under this run's own root make each
# selftest pass once per run per script; a failing selftest is never stamped, and the stamp tests are in
# scripts/test-selftest-stamps.sh.
export DCR_SELFTEST_STAMPS="$WORK/selftest-stamps"

# Documented SKILL.md size budget (bytes). Exceeding it must WARN, not fail.
SKILL_BUDGET=1024

cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# Hermeticity sentinel (own lane, asserted at the very end of this file):
# every case below must write only under $WORK, never into the checkout
# itself. Snapshot the checkout's status now; the final case compares it
# unchanged once every other case has run.
_root_sentinel="$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)"

pass=0
fail=0
GATE_RC=0

# record <0|1> <label>  — 0 == case passed, non-zero == case failed.
record() {
  if [ "$1" -eq 0 ]; then
    printf 'PASS  %s\n' "$2"
    pass=$((pass + 1))
  else
    printf 'FAIL  %s\n' "$2"
    fail=$((fail + 1))
  fi
}

# gate <cmd...> — run the tested helper through bash, capturing its REAL exit code into
# GATE_RC without masking it. Output is kept for postcondition inspection.
gate() {
  if bash "$@" >"$WORK/last.log" 2>&1; then
    GATE_RC=0
  else
    GATE_RC=$?
  fi
}

# ---------------------------------------------------------------------------
# precondition — the helper under test must exist as a regular file.
#
# Without this guard a missing scripts/ci-gates.sh would silently corrupt the
# result: a command that cannot run exits non-zero, and every rejection case
# reads a non-zero exit as success. The RED harness would then falsely go
# green while proving nothing. Fail loudly and early instead, so a missing
# helper makes this harness FAIL.
# ---------------------------------------------------------------------------
if [ ! -f "$GATES" ]; then
  printf 'PRECONDITION FAIL: helper file not found: %s\n' "$GATES" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# privacy — banlist hygiene and secret detection
# ---------------------------------------------------------------------------

mkdir -p "$WORK/scan"
# Build the planted secret at runtime so this harness file itself never carries
# a literal match for the repo's pre-commit secret grep.
planted="AKIA$(printf 'X%.0s' {1..16})"
printf 'aws_key = %s\n' "$planted" >"$WORK/scan/planted.txt"

# A valid banlist: comment plus a real pattern (the pattern text below does not
# itself match AKIA[0-9A-Z]{16}, so it is safe to commit).
printf '# known secret shapes\nAKIA[0-9A-Z]{16}\n' >"$WORK/banlist.valid"
: >"$WORK/banlist.empty"
printf '# only comments\n#   nothing actionable\n' >"$WORK/banlist.comments"

gate "$GATES" privacy --banlist "$WORK/banlist.empty" "$WORK/scan"
if [ "$GATE_RC" -ne 0 ]; then record 0 "privacy: reject empty banlist"; else record 1 "privacy: reject empty banlist"; fi

gate "$GATES" privacy --banlist "$WORK/banlist.comments" "$WORK/scan"
if [ "$GATE_RC" -ne 0 ]; then record 0 "privacy: reject all-comment banlist"; else record 1 "privacy: reject all-comment banlist"; fi

gate "$GATES" privacy --banlist "$WORK/banlist.valid" "$WORK/scan"
if [ "$GATE_RC" -ne 0 ]; then record 0 "privacy: detect planted banned secret"; else record 1 "privacy: detect planted banned secret"; fi

# A banlist carrying an invalid extended regular expression (a lone opening
# bracket has no closing `]`). The gate must fail closed: an unusable pattern
# cannot be silently skipped, because a skipped pattern scans nothing and lets a
# banned string through undetected. Reject the run instead.
#
# It must also fail *privately*: the banlist may hold real secret shapes, so a
# diagnostic that echoes the offending pattern would leak banlist content into
# CI logs. The planted invalid pattern here is a lone opening bracket `[`; the
# gate must therefore (a) exit non-zero, (b) say the offending content was
# withheld, and (c) never reproduce the `[` in its output. Fixed-string greps
# (-F) are used so the bracket is matched literally, not as a regex.
printf '# broken pattern below\n[\n' >"$WORK/banlist.badregex"
gate "$GATES" privacy --banlist "$WORK/banlist.badregex" "$WORK/scan"
if [ "$GATE_RC" -ne 0 ] \
  && grep -qiF 'content withheld' "$WORK/last.log" \
  && ! grep -qF '[' "$WORK/last.log"; then
  record 0 "privacy: reject banlist with invalid ERE (fail closed, without disclosing banlist content)"
else
  record 1 "privacy: reject banlist with invalid ERE (fail closed, without disclosing banlist content)"
fi

# The documented optional local override: a primary .banlist.txt is loaded
# together with its sibling .banlist.local.txt when that sibling exists, so an
# operator can extend the committed policy locally without editing it. This case
# proves BOTH files are loaded, not just the primary. The primary here carries a
# single valid pattern that deliberately does NOT match the planted secret, while
# the sibling local file carries the banned shape (the same AKIA[0-9A-Z]{16} regex
# already used above). If the gate read only the primary, the planted secret would
# slip through and the scan would report clean; the run must reject only because
# the sibling local banlist is loaded alongside the primary. Content stays hidden:
# no secret literal is written — the planted fixture is the runtime-built one from
# above, and only the regex shape (never a live key) is placed in the local file.
localdir="$WORK/banlist-local"
mkdir -p "$localdir"
printf '# primary policy (nonmatching)\nNOMATCH_[A-Z]+\n' >"$localdir/.banlist.txt"
printf 'AKIA[0-9A-Z]{16}\n' >"$localdir/.banlist.local.txt"

gate "$GATES" privacy --banlist "$localdir/.banlist.txt" "$WORK/scan"
if [ "$GATE_RC" -ne 0 ]; then
  record 0 "privacy: load optional sibling .banlist.local.txt alongside primary .banlist.txt"
else
  record 1 "privacy: load optional sibling .banlist.local.txt alongside primary .banlist.txt"
fi

# A tree too large for one argv (ARG_MAX) must still be scanned, and a hit in
# the last file must still block: the scan runs in chunks.
bigdir="$WORK/scan-big"
mkdir -p "$bigdir"
( cd "$bigdir" && seq -f "f%06g-padding-to-make-every-path-long-enough-to-overflow-one-argv-on-any-host.txt" 1 30000 | xargs touch )
printf 'aws_key = %s\n' "$planted" >"$bigdir/zz-last.txt"
gate "$GATES" privacy --banlist "$WORK/banlist.valid" "$bigdir"
if [ "$GATE_RC" -ne 0 ] && grep -q 'zz-last.txt' "$WORK/last.log"; then
  record 0 "privacy: a tree larger than ARG_MAX is scanned in chunks and the hit is found"
else
  record 1 "privacy: a tree larger than ARG_MAX is scanned in chunks and the hit is found"
fi
rm -f "$bigdir/zz-last.txt"
gate "$GATES" privacy --banlist "$WORK/banlist.valid" "$bigdir"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "privacy: a clean tree larger than ARG_MAX passes"
else
  record 1 "privacy: a clean tree larger than ARG_MAX passes"
fi

# A named pipe in the scanned tree must not hang the scan (stray fixture).
fifodir="$WORK/scan-fifo"
mkdir -p "$fifodir" && printf 'clean\n' >"$fifodir/ok.txt" && mkfifo "$fifodir/pipe"
( bash "$GATES" privacy --banlist "$WORK/banlist.valid" "$fifodir" >/dev/null 2>&1; echo $? >"$WORK/fifo.rc" ) &
fifo_pid=$!
for _ in $(seq 1 100); do kill -0 "$fifo_pid" 2>/dev/null || break; sleep 0.1; done
if kill -0 "$fifo_pid" 2>/dev/null; then
  kill "$fifo_pid" 2>/dev/null; pkill -f "privacy --banlist $WORK/banlist.valid $fifodir" 2>/dev/null
  record 1 "privacy: a FIFO in the tree does not hang the scan"
elif [ "$(cat "$WORK/fifo.rc")" = 0 ]; then
  record 0 "privacy: a FIFO in the tree does not hang the scan"
else
  record 1 "privacy: a FIFO in the tree does not hang the scan"
fi
rm -f "$fifodir/pipe"

# ---------------------------------------------------------------------------
# routing — every references/*.md must be routed from SKILL.md
# ---------------------------------------------------------------------------

unrouted="$WORK/skill-unrouted"
mkdir -p "$unrouted/references"
printf '# Skill\n\nSee references/routed.md for depth.\n' >"$unrouted/SKILL.md"
printf 'routed depth\n' >"$unrouted/references/routed.md"
printf 'orphaned depth\n' >"$unrouted/references/unrouted.md"

gate "$GATES" routing "$unrouted"
if [ "$GATE_RC" -ne 0 ]; then record 0 "routing: reject unrouted reference"; else record 1 "routing: reject unrouted reference"; fi

# Basenames must be matched literally, not as regexes. The reference file is
# references/literal.md, but SKILL.md only mentions references/literalXmd. If the
# gate treats the basename as a pattern, the `.` in `literal.md` matches the `X`
# in `literalXmd` and the orphan is falsely considered routed. A literal match
# sees no mention of literal.md, so the reference is unrouted and must be
# rejected.
literal="$WORK/skill-literal"
mkdir -p "$literal/references"
printf '# Skill\n\nSee references/literalXmd for depth.\n' >"$literal/SKILL.md"
printf 'literal depth\n' >"$literal/references/literal.md"

gate "$GATES" routing "$literal"
if [ "$GATE_RC" -ne 0 ]; then record 0 "routing: reject reference matched only via regex-meta basename"; else record 1 "routing: reject reference matched only via regex-meta basename"; fi

# Oversized, well-routed SKILL.md: the size ratchet FAILS on bloat (it used to
# only warn), and there is no per-skill allowlist, so it must fail with a SIZE
# FAIL diagnostic.
big="$WORK/skill-big"
mkdir -p "$big/references"
printf '# Skill\n\nSee references/routed.md for depth.\n' >"$big/SKILL.md"
head -c $((SKILL_BUDGET * 4)) </dev/zero | tr '\0' 'x' >>"$big/SKILL.md"
printf 'routed depth\n' >"$big/references/routed.md"

gate "$GATES" routing --max-bytes "$SKILL_BUDGET" "$big"
if [ "$GATE_RC" -ne 0 ] && grep -q 'SIZE FAIL' "$WORK/last.log"; then
  record 0 "routing: FAIL (not warn) when a SKILL.md exceeds the budget"
else
  record 1 "routing: FAIL (not warn) when a SKILL.md exceeds the budget"
fi

# The former size allowlist is gone: a skill dir named agentic-delivery (the one
# name the allowlist used to exempt) with the same oversized body now FAILS with
# SIZE FAIL and never prints SIZE ALLOWED. Planted RED against a re-added pin.
allow="$WORK/agentic-delivery"
mkdir -p "$allow/references"
printf '# Skill\n\nSee references/routed.md for depth.\n' >"$allow/SKILL.md"
head -c $((SKILL_BUDGET * 4)) </dev/zero | tr '\0' 'x' >>"$allow/SKILL.md"
printf 'routed depth\n' >"$allow/references/routed.md"

gate "$GATES" routing --max-bytes "$SKILL_BUDGET" "$allow"
if [ "$GATE_RC" -ne 0 ] && grep -q 'SIZE FAIL' "$WORK/last.log" \
  && ! grep -q 'SIZE ALLOWED' "$WORK/last.log"; then
  record 0 "routing: agentic-delivery is not size-allowlisted (oversized fixture FAILS)"
else
  record 1 "routing: agentic-delivery is not size-allowlisted (oversized fixture FAILS)"
fi

# The real agentic-delivery skill fits the CI cap on its own (routing ok, no
# SIZE ALLOWED escape hatch), so ci.yml's routing line enforces the cap on it.
gate "$GATES" routing --max-bytes 24000 "$ROOT/.claude/skills/agentic-delivery"
if [ "$GATE_RC" -eq 0 ] && ! grep -q 'SIZE' "$WORK/last.log"; then
  record 0 "routing: real agentic-delivery SKILL.md is within the 24000-byte cap"
else
  record 1 "routing: real agentic-delivery SKILL.md is within the 24000-byte cap"
fi

# ---------------------------------------------------------------------------
# size — frozen per-file BYTE-count budgets (scripts/size-budgets.tsv), the
# ratchet skill-authoring-and-size.md prescribes ("a documented budget,
# enforced"), applied to this repo's own SKILL.md/references files.
#
# Measured in bytes (`wc -c`), not lines: a line-count budget is beaten by
# packing more prose onto fewer, longer lines. The planted-RED case below
# proves that directly — it SHRINKS the fixture's line count while GROWING
# its byte count past budget, which a line-count gate would have missed.
# ---------------------------------------------------------------------------

sizeroot="$WORK/size-fixture/root"
mkdir -p "$sizeroot/.claude/skills/demo/references"
printf 'hello\nworld\n' >"$sizeroot/.claude/skills/demo/SKILL.md"        # 12 bytes, 2 lines
printf 'ab\n' >"$sizeroot/.claude/skills/demo/references/ref.md"        # 3 bytes, 1 line
printf '# unit: bytes\n# header comment\n.claude/skills/demo/SKILL.md\t12\n.claude/skills/demo/references/ref.md\t3\n' \
  >"$WORK/size-config.tsv"

gate "$GATES" size --config "$WORK/size-config.tsv" "$sizeroot"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "size: passes when every file is at or under its byte budget"
else
  record 1 "size: passes when every file is at or under its byte budget"
fi

# Planted RED, byte-vs-line: fewer lines (1 -> 0, no trailing newline) but MORE
# bytes (3 -> 8), past the frozen budget of 3. The gate must FIRE and name the
# offending file — proving it is truly measuring bytes, not lines.
printf 'abcdefgh' >"$sizeroot/.claude/skills/demo/references/ref.md"
gate "$GATES" size --config "$WORK/size-config.tsv" "$sizeroot"
if [ "$GATE_RC" -ne 0 ] && grep -q 'SIZE FAIL: .claude/skills/demo/references/ref.md is 8 bytes' "$WORK/last.log"; then
  record 0 "size: FIRES on a fixture that shrinks lines but grows bytes past budget (planted RED)"
else
  record 1 "size: FIRES on a fixture that shrinks lines but grows bytes past budget (planted RED)"
fi
# restore under-budget content so the cases below start clean
printf 'ab\n' >"$sizeroot/.claude/skills/demo/references/ref.md"

# Fail closed: a shipped file on disk with no row in the config.
printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t12\n' >"$WORK/size-config-missing.tsv"
gate "$GATES" size --config "$WORK/size-config-missing.tsv" "$sizeroot"
if [ "$GATE_RC" -ne 0 ] && grep -q 'SIZE MISSING BUDGET: .claude/skills/demo/references/ref.md' "$WORK/last.log"; then
  record 0 "size: fails closed on a shipped file absent from the config"
else
  record 1 "size: fails closed on a shipped file absent from the config"
fi

# Core cap: a non-allowlisted SKILL.md over 16000 bytes FIRES even within its row budget (planted RED).
capdir="$sizeroot/.claude/skills/bloat"; mkdir -p "$capdir"
head -c 16001 /dev/zero | tr '\0' 'a' >"$capdir/SKILL.md"
printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t12\n.claude/skills/demo/references/ref.md\t3\n.claude/skills/bloat/SKILL.md\t99999\n' \
  >"$WORK/size-config-cap.tsv"
gate "$GATES" size --config "$WORK/size-config-cap.tsv" "$sizeroot"
if [ "$GATE_RC" -ne 0 ] && grep -q 'core cap 16000' "$WORK/last.log"; then
  record 0 "size: FIRES on a non-allowlisted SKILL.md over the 16000-byte core cap (planted RED)"
else
  record 1 "size: FIRES on a non-allowlisted SKILL.md over the 16000-byte core cap (planted RED)"
fi
rm -f "$capdir/SKILL.md"; rmdir "$capdir"

# Fail closed: a config row naming a file that no longer exists on disk.
printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t12\n.claude/skills/demo/references/ref.md\t3\n.claude/skills/demo/references/ghost.md\t5\n' \
  >"$WORK/size-config-dangling.tsv"
gate "$GATES" size --config "$WORK/size-config-dangling.tsv" "$sizeroot"
if [ "$GATE_RC" -ne 0 ] && grep -q 'SIZE DANGLING: .claude/skills/demo/references/ghost.md' "$WORK/last.log"; then
  record 0 "size: fails closed on a config row whose file no longer exists"
else
  record 1 "size: fails closed on a config row whose file no longer exists"
fi

# Fail closed: a config without the `# unit: bytes` declaration. Otherwise a
# change could delete the line (size stays green), then re-add it together with
# a raise, and size-ratchet would read the base as pre-byte-adoption and skip.
printf '.claude/skills/demo/SKILL.md\t12\n.claude/skills/demo/references/ref.md\t3\n' \
  >"$WORK/size-config-nounit.tsv"
gate "$GATES" size --config "$WORK/size-config-nounit.tsv" "$sizeroot"
if [ "$GATE_RC" -ne 0 ] && grep -q "lacks the required '# unit: bytes' line" "$WORK/last.log"; then
  record 0 "size: fails closed when the config lacks the '# unit: bytes' line"
else
  record 1 "size: fails closed when the config lacks the '# unit: bytes' line"
fi

# The real repo config passes against the real repo tree: this change
# re-baselined every row at today's exact byte size, so it is green day one
# (the freeze-ratchet).
gate "$GATES" size --config "$ROOT/scripts/size-budgets.tsv" "$ROOT"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "size: the real repo's SKILL.md/references files are all within their frozen byte budget"
else
  record 1 "size: the real repo's SKILL.md/references files are all within their frozen byte budget"
fi

# ---------------------------------------------------------------------------
# size-ratchet — CI-checkable enforcement that no scripts/size-budgets.tsv row
# may increase vs a base ref without an explicit `size-budget-raise:` marker
# line in the commit range or CHANGELOG.md. Own fixture repo (needs real git
# commits, unlike the plain `git add` fixtures above) and own block.
# ---------------------------------------------------------------------------

ratchetroot="$WORK/ratchet-fixture/root"
mkdir -p "$ratchetroot/.claude/skills/demo/references"
git -C "$ratchetroot" init -q
git -C "$ratchetroot" config user.email "test@example.com"
git -C "$ratchetroot" config user.name "Test"
mkdir -p "$ratchetroot/scripts"
printf 'hello\nworld\n' >"$ratchetroot/.claude/skills/demo/SKILL.md"
printf 'ab\n' >"$ratchetroot/.claude/skills/demo/references/ref.md"
printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t12\n.claude/skills/demo/references/ref.md\t3\n' \
  >"$ratchetroot/scripts/size-budgets.tsv"
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm base >/dev/null 2>&1
ratchet_base="$(git -C "$ratchetroot" rev-parse HEAD)"

# Case A: shrink a row -> no marker needed, passes.
printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t10\n.claude/skills/demo/references/ref.md\t3\n' \
  >"$ratchetroot/scripts/size-budgets.tsv"
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm shrink >/dev/null 2>&1

gate "$GATES" size-ratchet --base "$ratchet_base" --config "$ratchetroot/scripts/size-budgets.tsv" "$ratchetroot"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "size-ratchet: a shrunk row needs no marker and passes"
else
  record 1 "size-ratchet: a shrunk row needs no marker and passes"
fi

# Case B: planted RED — a raised row with NO marker anywhere must FAIL.
git -C "$ratchetroot" reset --hard "$ratchet_base" -q >/dev/null 2>&1
printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t20\n.claude/skills/demo/references/ref.md\t3\n' \
  >"$ratchetroot/scripts/size-budgets.tsv"
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "raise no marker" >/dev/null 2>&1

gate "$GATES" size-ratchet --base "$ratchet_base" --config "$ratchetroot/scripts/size-budgets.tsv" "$ratchetroot"
if [ "$GATE_RC" -ne 0 ] && grep -q 'RATCHET FAIL: .claude/skills/demo/SKILL.md raised 12->20' "$WORK/last.log"; then
  record 0 "size-ratchet: FIRES on an undocumented raise and names the row (planted RED)"
else
  record 1 "size-ratchet: FIRES on an undocumented raise and names the row (planted RED)"
fi

# Case C: the SAME raise, but the marker is in the commit message -> passes.
git -C "$ratchetroot" reset --hard "$ratchet_base" -q >/dev/null 2>&1
printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t20\n.claude/skills/demo/references/ref.md\t3\n' \
  >"$ratchetroot/scripts/size-budgets.tsv"
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "raise with marker

size-budget-raise: .claude/skills/demo/SKILL.md 12→20 fixture growth is deliberate" >/dev/null 2>&1

gate "$GATES" size-ratchet --base "$ratchet_base" --config "$ratchetroot/scripts/size-budgets.tsv" "$ratchetroot"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "size-ratchet: a raise with a commit-message marker passes"
else
  record 1 "size-ratchet: a raise with a commit-message marker passes"
fi

# Case D: the SAME raise, marker instead lives in CHANGELOG.md -> passes.
git -C "$ratchetroot" reset --hard "$ratchet_base" -q >/dev/null 2>&1
printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t20\n.claude/skills/demo/references/ref.md\t3\n' \
  >"$ratchetroot/scripts/size-budgets.tsv"
printf 'size-budget-raise: .claude/skills/demo/SKILL.md 12→20 fixture growth is deliberate\n' \
  >"$ratchetroot/CHANGELOG.md"
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "raise with changelog marker" >/dev/null 2>&1

gate "$GATES" size-ratchet --base "$ratchet_base" --config "$ratchetroot/scripts/size-budgets.tsv" "$ratchetroot"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "size-ratchet: a raise with a CHANGELOG.md marker passes"
else
  record 1 "size-ratchet: a raise with a CHANGELOG.md marker passes"
fi

# Case E: fail closed on an unresolvable base ref.
gate "$GATES" size-ratchet --base "totally-bogus-ref-xyz" --config "$ratchetroot/scripts/size-budgets.tsv" "$ratchetroot"
if [ "$GATE_RC" -ne 0 ] && grep -qi 'unresolvable base' "$WORK/last.log"; then
  record 0 "size-ratchet: fails closed on an unresolvable base ref"
else
  record 1 "size-ratchet: fails closed on an unresolvable base ref"
fi

# Case F: planted RED — a marker that ALREADY exists in the base's CHANGELOG.md
# must not approve a new raise; only lines the change itself adds count.
git -C "$ratchetroot" reset --hard "$ratchet_base" -q >/dev/null 2>&1
printf 'size-budget-raise: .claude/skills/demo/SKILL.md 12→20 an older, unrelated raise\n' \
  >"$ratchetroot/CHANGELOG.md"
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "base with an old marker" >/dev/null 2>&1
ratchet_base_log="$(git -C "$ratchetroot" rev-parse HEAD)"
printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t20\n.claude/skills/demo/references/ref.md\t3\n' \
  >"$ratchetroot/scripts/size-budgets.tsv"
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "raise relying on the old marker" >/dev/null 2>&1
gate "$GATES" size-ratchet --base "$ratchet_base_log" --config "$ratchetroot/scripts/size-budgets.tsv" "$ratchetroot"
if [ "$GATE_RC" -ne 0 ] && grep -q 'RATCHET FAIL: .claude/skills/demo/SKILL.md raised 12->20' "$WORK/last.log"; then
  record 0 "size-ratchet: an old marker in the pre-existing CHANGELOG does not approve a new raise (planted RED)"
else
  record 1 "size-ratchet: an old marker in the pre-existing CHANGELOG does not approve a new raise (planted RED)"
fi

# Case G: planted RED — re-wording the old marker line (the diff now shows it
# as an ADDED line) still must not approve the raise: the base already has it.
printf 'size-budget-raise: .claude/skills/demo/SKILL.md 12→20 re-dated reason\n' \
  >"$ratchetroot/CHANGELOG.md"
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "re-word the old marker" >/dev/null 2>&1
gate "$GATES" size-ratchet --base "$ratchet_base_log" --config "$ratchetroot/scripts/size-budgets.tsv" "$ratchetroot"
if [ "$GATE_RC" -ne 0 ] && grep -q 'RATCHET FAIL: .claude/skills/demo/SKILL.md raised 12->20' "$WORK/last.log"; then
  record 0 "size-ratchet: a re-worded (re-added) old CHANGELOG marker does not approve a new raise (planted RED)"
else
  record 1 "size-ratchet: a re-worded (re-added) old CHANGELOG marker does not approve a new raise (planted RED)"
fi

# Case H: fail closed when the working-tree config lacks '# unit: bytes'.
git -C "$ratchetroot" reset --hard "$ratchet_base" -q >/dev/null 2>&1
printf '.claude/skills/demo/SKILL.md\t12\n.claude/skills/demo/references/ref.md\t3\n' \
  >"$ratchetroot/scripts/size-budgets.tsv"
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "drop the unit line" >/dev/null 2>&1
gate "$GATES" size-ratchet --base "$ratchet_base" --config "$ratchetroot/scripts/size-budgets.tsv" "$ratchetroot"
if [ "$GATE_RC" -ne 0 ] && grep -q "lacks the required '# unit: bytes' line" "$WORK/last.log"; then
  record 0 "size-ratchet: fails closed when the working-tree config lacks the '# unit: bytes' line"
else
  record 1 "size-ratchet: fails closed when the working-tree config lacks the '# unit: bytes' line"
fi

# Case I: the one legitimate skip — the BASE config predates byte adoption (no
# unit line, line-count rows), so rows are not comparable and nothing ratchets.
git -C "$ratchetroot" reset --hard "$ratchet_base" -q >/dev/null 2>&1
printf '.claude/skills/demo/SKILL.md\t2\n.claude/skills/demo/references/ref.md\t1\n' \
  >"$ratchetroot/scripts/size-budgets.tsv"
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "pre-adoption line-count base" >/dev/null 2>&1
ratchet_base_lines="$(git -C "$ratchetroot" rev-parse HEAD)"
printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t12\n.claude/skills/demo/references/ref.md\t3\n' \
  >"$ratchetroot/scripts/size-budgets.tsv"
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "adopt bytes" >/dev/null 2>&1
gate "$GATES" size-ratchet --base "$ratchet_base_lines" --config "$ratchetroot/scripts/size-budgets.tsv" "$ratchetroot"
if [ "$GATE_RC" -eq 0 ] && grep -q 'pre-byte adoption' "$WORK/last.log"; then
  record 0 "size-ratchet: skips only when the base config predates byte adoption"
else
  record 1 "size-ratchet: skips only when the base config predates byte adoption"
fi

# Case J: a row is dropped, but its file was ALSO deleted -> legitimate, passes.
git -C "$ratchetroot" reset --hard "$ratchet_base" -q >/dev/null 2>&1
git -C "$ratchetroot" rm -q "$ratchetroot/.claude/skills/demo/references/ref.md" >/dev/null 2>&1
printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t12\n' \
  >"$ratchetroot/scripts/size-budgets.tsv"
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "drop row for a file that was deleted" >/dev/null 2>&1

gate "$GATES" size-ratchet --base "$ratchet_base" --config "$ratchetroot/scripts/size-budgets.tsv" "$ratchetroot"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "size-ratchet: dropping a row for a file also deleted needs no marker and passes"
else
  record 1 "size-ratchet: dropping a row for a file also deleted needs no marker and passes"
fi

# Case K: planted RED — a row is dropped while its file STILL exists (the
# README.md-row regression this case guards against). No marker can approve a
# silent deletion; it must FAIL and name the row.
git -C "$ratchetroot" reset --hard "$ratchet_base" -q >/dev/null 2>&1
printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t12\n' \
  >"$ratchetroot/scripts/size-budgets.tsv"
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "silently drop row for a file that still exists" >/dev/null 2>&1

gate "$GATES" size-ratchet --base "$ratchet_base" --config "$ratchetroot/scripts/size-budgets.tsv" "$ratchetroot"
if [ "$GATE_RC" -ne 0 ] && grep -q 'RATCHET FAIL: .claude/skills/demo/references/ref.md had a budget row' "$WORK/last.log"; then
  record 0 "size-ratchet: FIRES when a row is silently dropped for a file that still exists (planted RED)"
else
  record 1 "size-ratchet: FIRES when a row is silently dropped for a file that still exists (planted RED)"
fi

# Cases L-P: a base whose rows are stale (lanes do not commit rows, so an unlanded wave leaves them behind).
# The raise is measured from the larger of the base row and the file's real size at base.
git -C "$ratchetroot" reset --hard "$ratchet_base" -q >/dev/null 2>&1
printf '%020d' 0 >"$ratchetroot/.claude/skills/demo/SKILL.md"   # 20 bytes at base, row still 12
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "stale base: file grew past its row" >/dev/null 2>&1
ratchet_stale="$(git -C "$ratchetroot" rev-parse HEAD)"
ratchet_cfg="$ratchetroot/scripts/size-budgets.tsv"
stale_rows() { printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t%s\n.claude/skills/demo/references/ref.md\t3\n' "$1" >"$ratchet_cfg"; }

# L: the file is untouched and its row is regenerated to the real size: not a raise.
stale_rows 20
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "regen rows" >/dev/null 2>&1
gate "$GATES" size-ratchet --base "$ratchet_stale" --config "$ratchet_cfg" "$ratchetroot"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "size-ratchet: an untouched file with a stale base row passes"
else
  record 1 "size-ratchet: an untouched file with a stale base row passes"
fi

# M: planted RED — real growth 20 -> 30 with no marker fails, measured from the real base size.
git -C "$ratchetroot" reset --hard "$ratchet_stale" -q >/dev/null 2>&1
printf '%030d' 0 >"$ratchetroot/.claude/skills/demo/SKILL.md"; stale_rows 30
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "grow" >/dev/null 2>&1
gate "$GATES" size-ratchet --base "$ratchet_stale" --config "$ratchet_cfg" "$ratchetroot"
if [ "$GATE_RC" -ne 0 ] && grep -q 'RATCHET FAIL: .claude/skills/demo/SKILL.md raised 20->30' "$WORK/last.log"; then
  record 0 "size-ratchet: real growth on a stale base is measured from the real size (planted RED)"
else
  record 1 "size-ratchet: real growth on a stale base is measured from the real size (planted RED)"
fi

# N: the marker names the real base size and passes.
git -C "$ratchetroot" reset --hard "$ratchet_stale" -q >/dev/null 2>&1
printf '%030d' 0 >"$ratchetroot/.claude/skills/demo/SKILL.md"; stale_rows 30
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "grow with marker

size-budget-raise: .claude/skills/demo/SKILL.md 20→30 fixture growth is deliberate" >/dev/null 2>&1
gate "$GATES" size-ratchet --base "$ratchet_stale" --config "$ratchet_cfg" "$ratchetroot"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "size-ratchet: growth with a marker naming the real base size passes"
else
  record 1 "size-ratchet: growth with a marker naming the real base size passes"
fi

# O: planted RED — a marker built on the stale row (12->30) does not approve the growth.
git -C "$ratchetroot" reset --hard "$ratchet_stale" -q >/dev/null 2>&1
printf '%030d' 0 >"$ratchetroot/.claude/skills/demo/SKILL.md"; stale_rows 30
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "grow with a stale-row marker

size-budget-raise: .claude/skills/demo/SKILL.md 12→30 stale" >/dev/null 2>&1
gate "$GATES" size-ratchet --base "$ratchet_stale" --config "$ratchet_cfg" "$ratchetroot"
if [ "$GATE_RC" -ne 0 ] && grep -q 'RATCHET FAIL: .claude/skills/demo/SKILL.md raised 20->30' "$WORK/last.log"; then
  record 0 "size-ratchet: a marker built on the stale row does not approve growth (planted RED)"
else
  record 1 "size-ratchet: a marker built on the stale row does not approve growth (planted RED)"
fi

# P: planted RED — a hand-kept row above the size is a budget: base 20 bytes with row 50, head 60 bytes with
# row 60 and no marker fails naming 50->60 (a rule that dropped the row floor would name 20->60).
git -C "$ratchetroot" reset --hard "$ratchet_base" -q >/dev/null 2>&1
printf '%020d' 0 >"$ratchetroot/.claude/skills/demo/SKILL.md"; stale_rows 50
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "base: hand-kept budget row above the size" >/dev/null 2>&1
ratchet_budget="$(git -C "$ratchetroot" rev-parse HEAD)"
printf '%060d' 0 >"$ratchetroot/.claude/skills/demo/SKILL.md"; stale_rows 60
git -C "$ratchetroot" add -A >/dev/null 2>&1
git -C "$ratchetroot" commit -qm "grow past the hand-kept budget" >/dev/null 2>&1
gate "$GATES" size-ratchet --base "$ratchet_budget" --config "$ratchet_cfg" "$ratchetroot"
if [ "$GATE_RC" -ne 0 ] && grep -q 'RATCHET FAIL: .claude/skills/demo/SKILL.md raised 50->60' "$WORK/last.log"; then
  record 0 "size-ratchet: a hand-kept budget row above the size keeps the row floor (planted RED)"
else
  record 1 "size-ratchet: a hand-kept budget row above the size keeps the row floor (planted RED)"
fi

# The real repo's config carries every row it had at origin/main's tip that
# this branch's base still ships (proves the README.md-row regression can't
# recur silently in the real config, not only the synthetic fixture above).
gate "$GATES" size-ratchet --base "origin/main" --config "$ROOT/scripts/size-budgets.tsv" "$ROOT"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "size-ratchet: the real repo config drops no row for a file that still exists vs origin/main"
else
  record 1 "size-ratchet: the real repo config drops no row for a file that still exists vs origin/main"
fi

# Every overlay flag that ADDS a skill (a WITH_* var guarding a SKILLS+= block)
# must also appear in the AGENTS.md overlay-stamp guard, or a standalone
# --with-<x> install lands the skill but writes no stamp — the guard-omission bug
# that silently affected six overlays until it was fixed (#82, #83).
guard_vars="$(grep -B1 'OVERLAY_LINES=""' "$ROOT/install.sh" | grep -oE 'WITH_[A-Z_]+' | sort -u)"
skill_vars="$(grep -B1 'SKILLS+=(' "$ROOT/install.sh" | grep -oE 'WITH_[A-Z_]+' | sort -u)"
stamp_missing="$(comm -23 <(printf '%s\n' "$skill_vars") <(printf '%s\n' "$guard_vars"))"
if [ -z "$stamp_missing" ]; then
  record 0 "install: every skill-adding overlay flag is in the AGENTS.md stamp guard"
else
  printf 'STAMP-GUARD MISSING: %s\n' "$(printf '%s' "$stamp_missing" | tr '\n' ' ')" >&2
  record 1 "install: every skill-adding overlay flag is in the AGENTS.md stamp guard"
fi

# ---------------------------------------------------------------------------
# binaries — extension-scoped block on committed images/media/archives/build
# output; scans only git-TRACKED files, with a small path-scoped allowlist.
# ---------------------------------------------------------------------------

binclean="$WORK/binaries-clean"
mkdir -p "$binclean"
git -C "$binclean" init -q
printf 'hello world\n' >"$binclean/notes.txt"
git -C "$binclean" add notes.txt >/dev/null 2>&1

gate "$GATES" binaries "$binclean"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "binaries: a tracked tree with no banned-extension file passes"
else
  record 1 "binaries: a tracked tree with no banned-extension file passes"
fi

# Planted RED: a demo screenshot-shaped binary, git-tracked, unrouted through
# any allowlist. The gate must FIRE, name the exact path, and point at an
# artifact store instead of silently accepting it.
binfire="$WORK/binaries-fire"
mkdir -p "$binfire"
git -C "$binfire" init -q
printf 'hello world\n' >"$binfire/notes.txt"
printf 'not a real png -- a planted demo binary artifact\n' >"$binfire/demo.png"
git -C "$binfire" add notes.txt demo.png >/dev/null 2>&1

gate "$GATES" binaries "$binfire"
if [ "$GATE_RC" -ne 0 ] \
  && grep -q 'BINARY TRACKED: demo.png' "$WORK/last.log" \
  && grep -qi 'route to an artifact store' "$WORK/last.log"; then
  record 0 "binaries: FIRES on a planted git-tracked demo.png and names it (planted RED)"
else
  record 1 "binaries: FIRES on a planted git-tracked demo.png and names it (planted RED)"
fi

# Discrimination: the SAME tracked demo.png, but now named in the tree's own
# scripts/binaries-allowlist.tsv, passes -- proving the allowlist actually
# exempts a path, not merely that an empty/absent allowlist parses.
binallow="$WORK/binaries-allowlisted"
mkdir -p "$binallow/scripts"
git -C "$binallow" init -q
printf 'hello world\n' >"$binallow/notes.txt"
printf 'not a real png -- a planted demo binary artifact\n' >"$binallow/demo.png"
printf '# fixture allowlist\ndemo.png\n' >"$binallow/scripts/binaries-allowlist.tsv"
git -C "$binallow" add notes.txt demo.png >/dev/null 2>&1

gate "$GATES" binaries "$binallow"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "binaries: an allowlisted tracked path is exempted, not flagged"
else
  record 1 "binaries: an allowlisted tracked path is exempted, not flagged"
fi

# The real repo tree passes today: scripts/binaries-allowlist.tsv was seeded
# empty because no tracked file currently matches a banned extension (the
# gate is GREEN by construction, same freeze-ratchet discipline as size).
gate "$GATES" binaries "$ROOT"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "binaries: the real repo has no un-allowlisted git-tracked banned-extension file"
else
  record 1 "binaries: the real repo has no un-allowlisted git-tracked banned-extension file"
fi

# Stale allowlist row: demo.png is named in scripts/binaries-allowlist.tsv but
# was never committed (the fix that removed it forgot to remove its row).
# FIRES, names the row, points at the allowlist file -- the same PR that
# fixes an allowlisted violation must drop that violation's row (#1198).
binstale="$WORK/binaries-stale"
mkdir -p "$binstale/scripts"
git -C "$binstale" init -q
printf 'hello world\n' >"$binstale/notes.txt"
printf '# fixture allowlist\ndemo.png\n' >"$binstale/scripts/binaries-allowlist.tsv"
git -C "$binstale" add notes.txt scripts/binaries-allowlist.tsv >/dev/null 2>&1

gate "$GATES" binaries "$binstale"
if [ "$GATE_RC" -ne 0 ] \
  && grep -q 'STALE ALLOWLIST ENTRY: demo.png' "$WORK/last.log"; then
  record 0 "binaries: FIRES on a stale allowlist row for a fixed violation (planted RED)"
else
  record 1 "binaries: FIRES on a stale allowlist row for a fixed violation (planted RED)"
fi

# ---------------------------------------------------------------------------
# mustload — frozen per-archetype MUST-LOAD token-est ceilings, parsed live
# from a fixture SKILL.md's own "Archetype -> load map" table (never the real
# repo's archetypes, so this harness never drifts as refs are edited).
# ---------------------------------------------------------------------------

mlroot="$WORK/mustload-fixture/root"
mkdir -p "$mlroot/.claude/skills/deep-code-review/references"
cat >"$mlroot/.claude/skills/deep-code-review/SKILL.md" <<'EOF'
# Fixture skill

| Archetype | Default domains | Must-load refs |
|---|---|---|
| demo | A B | `ref-a.md`, `ref-b.md` |
| demo2 | C | `ref-c.md` |

| Phase | Does | Load |
|---|---|---|
| 0 Map | fixture phase 0 | `ref-p1.md`, `ref-p4.md` on FULL |
| 1 Ground truth | fixture phase 1 | `ref-p1.md`, `ref-p2.md` |
| 2 Domain audits | fixture phase 2 | `ref-p3.md` + per-domain refs |
EOF
# ref-a.md = 40 bytes (10 tokens), ref-b.md = 20 bytes (5 tokens): demo totals
# 15. ref-c.md = 40 bytes (10 tokens): demo2 totals 10. chars/4, floor; head -c
# writes exactly N bytes, no trailing newline, so the math is exact.
head -c 40 </dev/zero | tr '\0' 'a' >"$mlroot/.claude/skills/deep-code-review/references/ref-a.md"
head -c 20 </dev/zero | tr '\0' 'b' >"$mlroot/.claude/skills/deep-code-review/references/ref-b.md"
head -c 40 </dev/zero | tr '\0' 'c' >"$mlroot/.claude/skills/deep-code-review/references/ref-c.md"

# Phase 0-2 mandatory-floor fixture refs, deliberately disjoint from the
# archetype refs above so growing one never perturbs the other's totals.
# ref-p1.md (10 tokens) is named in BOTH phase 0 and phase 1's Load column,
# proving the dedup: it must count once, not twice. ref-p2.md (5 tokens) and
# ref-p3.md (10 tokens) are LIGHT-only. ref-p4.md (20 tokens) is the sole
# "on FULL" ref, added only to the FULL total.
head -c 40 </dev/zero | tr '\0' 'd' >"$mlroot/.claude/skills/deep-code-review/references/ref-p1.md"
head -c 20 </dev/zero | tr '\0' 'e' >"$mlroot/.claude/skills/deep-code-review/references/ref-p2.md"
head -c 40 </dev/zero | tr '\0' 'f' >"$mlroot/.claude/skills/deep-code-review/references/ref-p3.md"
head -c 80 </dev/zero | tr '\0' 'g' >"$mlroot/.claude/skills/deep-code-review/references/ref-p4.md"

# SKILL.md's own byte count is part of the floor too (computed, not
# hand-counted, so a future edit to this fixture's heredoc can't silently
# desync the ceiling below).
ml_skill_bytes="$(wc -c <"$mlroot/.claude/skills/deep-code-review/SKILL.md" | tr -d '[:space:]')"
ml_skill_tok=$(( ml_skill_bytes / 4 ))
ml_floor_light=$(( ml_skill_tok + 10 + 5 + 10 ))
ml_floor_full=$(( ml_floor_light + 20 ))

printf 'demo\t15\ndemo2\t10\nphase-floor-light\t%d\nphase-floor-full\t%d\n' \
  "$ml_floor_light" "$ml_floor_full" >"$WORK/mustload-clean.tsv"
gate "$GATES" mustload --config "$WORK/mustload-clean.tsv" "$mlroot"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "mustload: passes when every archetype is at or under its frozen ceiling"
else
  record 1 "mustload: passes when every archetype is at or under its frozen ceiling"
fi

# Planted RED: grow demo's ref-b.md past its share of the ceiling (total
# becomes 10+50=60 > 15). The gate must FIRE and name "demo", leaving
# "demo2" (unaffected, still exactly at its own ceiling) unflagged.
head -c 200 </dev/zero | tr '\0' 'b' >"$mlroot/.claude/skills/deep-code-review/references/ref-b.md"
gate "$GATES" mustload --config "$WORK/mustload-clean.tsv" "$mlroot"
if [ "$GATE_RC" -ne 0 ] \
  && grep -q 'MUSTLOAD FAIL: archetype "demo"' "$WORK/last.log" \
  && ! grep -qE 'MUSTLOAD (FAIL|MISSING BUDGET|DANGLING): archetype "demo2"' "$WORK/last.log"; then
  record 0 "mustload: FIRES on an archetype over its frozen ceiling and names it (planted RED)"
else
  record 1 "mustload: FIRES on an archetype over its frozen ceiling and names it (planted RED)"
fi
# restore under-ceiling content so the cases below start clean
head -c 20 </dev/zero | tr '\0' 'b' >"$mlroot/.claude/skills/deep-code-review/references/ref-b.md"

# Fail closed: an archetype the load map defines (demo) with no row in the
# config, while a sibling archetype (demo2) IS present and satisfied -- the
# failure must name demo, not demo2.
printf 'demo2\t10\n' >"$WORK/mustload-missing.tsv"
gate "$GATES" mustload --config "$WORK/mustload-missing.tsv" "$mlroot"
if [ "$GATE_RC" -ne 0 ] \
  && grep -q 'MUSTLOAD MISSING BUDGET: archetype "demo"' "$WORK/last.log" \
  && ! grep -qE 'MUSTLOAD (FAIL|MISSING BUDGET|DANGLING): archetype "demo2"' "$WORK/last.log"; then
  record 0 "mustload: fails closed on an un-budgeted archetype (planted RED)"
else
  record 1 "mustload: fails closed on an un-budgeted archetype (planted RED)"
fi

# Fail closed: a config row naming an archetype the load map no longer
# defines ("ghost") must fail and name ghost, while demo/demo2 (both valid
# and satisfied) are not flagged.
printf 'demo\t15\ndemo2\t10\nghost\t5\n' >"$WORK/mustload-dangling.tsv"
gate "$GATES" mustload --config "$WORK/mustload-dangling.tsv" "$mlroot"
if [ "$GATE_RC" -ne 0 ] \
  && grep -q 'MUSTLOAD DANGLING: archetype "ghost"' "$WORK/last.log" \
  && ! grep -qE 'MUSTLOAD (FAIL|MISSING BUDGET|DANGLING): archetype "demo2?"' "$WORK/last.log"; then
  record 0 "mustload: fails closed on a config row whose archetype no longer exists (planted RED)"
else
  record 1 "mustload: fails closed on a config row whose archetype no longer exists (planted RED)"
fi

# The real repo config passes against the real repo tree: adding this gate
# touched no skill content, so it must be green day one (the freeze-ratchet).
gate "$GATES" mustload --config "$ROOT/scripts/mustload-budgets.tsv" "$ROOT"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "mustload: the real repo's archetypes are all within their frozen ceiling"
else
  record 1 "mustload: the real repo's archetypes are all within their frozen ceiling"
fi

# ---------------------------------------------------------------------------
# mustload — Phase 0-2 mandatory floor: `phase-floor-light` / `phase-floor-
# full`, parsed live from the same fixture SKILL.md's "| Phase | Does |
# Load |" table (never a second hardcoded copy of that list -- see
# scripts/ci-gates.sh cmd_mustload). Separate END block per case, reusing
# the mlroot fixture built above.
# ---------------------------------------------------------------------------

# Planted RED: grow the floor-only ref-p2.md (untouched by any archetype)
# past the LIGHT ceiling. Must FIRE naming phase-floor-light, while the
# unrelated archetype rows (demo/demo2) stay unflagged.
head -c 400 </dev/zero | tr '\0' 'e' >"$mlroot/.claude/skills/deep-code-review/references/ref-p2.md"
gate "$GATES" mustload --config "$WORK/mustload-clean.tsv" "$mlroot"
if [ "$GATE_RC" -ne 0 ] \
  && grep -q 'MUSTLOAD FLOOR FAIL: phase-floor-light' "$WORK/last.log" \
  && ! grep -qE 'MUSTLOAD (FAIL|MISSING BUDGET|DANGLING): archetype "demo2?"' "$WORK/last.log"; then
  record 0 "mustload: FLOOR FIRES when Phase 0-2 mandatory refs grow past their frozen ceiling (planted RED)"
else
  record 1 "mustload: FLOOR FIRES when Phase 0-2 mandatory refs grow past their frozen ceiling (planted RED)"
fi
# restore under-ceiling content so later cases (and other worktrees sharing
# this fixture pattern) start clean
head -c 20 </dev/zero | tr '\0' 'e' >"$mlroot/.claude/skills/deep-code-review/references/ref-p2.md"

# Fail closed: a SKILL.md with a valid Archetype -> load map table but NO
# "| Phase | Does | Load |" table at all must fail closed naming the
# unparseable section, before any archetype-level check even runs.
noph="$WORK/mustload-fixture/noph"
mkdir -p "$noph/.claude/skills/deep-code-review/references"
cat >"$noph/.claude/skills/deep-code-review/SKILL.md" <<'EOF'
# Fixture skill (no Phase table)

| Archetype | Default domains | Must-load refs |
|---|---|---|
| demo | A B | `ref-x.md` |
EOF
head -c 40 </dev/zero | tr '\0' 'x' >"$noph/.claude/skills/deep-code-review/references/ref-x.md"
printf 'demo\t999\nphase-floor-light\t999\nphase-floor-full\t999\n' >"$WORK/mustload-noph.tsv"
gate "$GATES" mustload --config "$WORK/mustload-noph.tsv" "$noph"
if [ "$GATE_RC" -ne 0 ] \
  && grep -q 'no Phase 0-2 mandatory refs parsed' "$WORK/last.log"; then
  record 0 "mustload: fails closed when SKILL.md has no parseable Phase 0-2 table (planted RED)"
else
  record 1 "mustload: fails closed when SKILL.md has no parseable Phase 0-2 table (planted RED)"
fi

# Fail closed: a mandatory phase row renamed out of the "<digit> <name>"
# shape used to be skipped silently, shrinking the floor while the gate
# stayed green. Each variant copies the clean mlroot fixture, rewrites one
# row, and gives every ceiling generous headroom so ONLY the missing-phase
# check can fail.
printf 'demo\t999\ndemo2\t999\nphase-floor-light\t9999\nphase-floor-full\t9999\n' \
  >"$WORK/mustload-phren.tsv"
for phren in '1 Ground truth|1. Ground truth|1' '2 Domain audits|Phase 2 Domain audits|2'; do
  phren_from="${phren%%|*}"
  phren_rest="${phren#*|}"
  phren_to="${phren_rest%%|*}"
  phren_num="${phren_rest#*|}"
  phren_root="$WORK/mustload-fixture/phren-$phren_num"
  rm -rf "$phren_root"
  cp -R "$mlroot" "$phren_root"
  sed "s/^| $phren_from |/| $phren_to |/" "$mlroot/.claude/skills/deep-code-review/SKILL.md" \
    >"$phren_root/.claude/skills/deep-code-review/SKILL.md"
  gate "$GATES" mustload --config "$WORK/mustload-phren.tsv" "$phren_root"
  if [ "$GATE_RC" -ne 0 ] \
    && grep -q "missing mandatory phase row(s): $phren_num " "$WORK/last.log"; then
    record 0 "mustload: fails closed when phase row $phren_num is renamed to \"$phren_to\" (planted RED)"
  else
    record 1 "mustload: fails closed when phase row $phren_num is renamed to \"$phren_to\" (planted RED)"
  fi
done

# CONDITIONAL qualifier: a Phase 0-2 ref written "`ref.md` when <trigger>" is a
# routed sub-file loaded only on that trigger -- excluded from both floors,
# but it must exist on disk. Three cases on a copy of the clean fixture, with
# a deliberately huge conditional ref (1000 tokens) so counting it by mistake
# would blow straight through the ceiling:
#   (a) "when" -> excluded: the gate passes and reports the unchanged floor;
#   (b) positive control -- the same ref WITHOUT "when" is counted and FIRES,
#       proving the qualifier (not the ref's mere presence) excludes it;
#   (c) the conditional ref missing on disk fails closed, naming it.
cond_root="$WORK/mustload-fixture/cond"
rm -rf "$cond_root"
cp -R "$mlroot" "$cond_root"
sed 's/^| 1 Ground truth | fixture phase 1 | `ref-p1.md`, `ref-p2.md` |$/| 1 Ground truth | fixture phase 1 | `ref-p1.md`, `ref-p2.md`; `ref-p5.md` when a gate verdict is disputed |/' \
  "$mlroot/.claude/skills/deep-code-review/SKILL.md" >"$cond_root/.claude/skills/deep-code-review/SKILL.md"
head -c 4000 </dev/zero | tr '\0' 'h' >"$cond_root/.claude/skills/deep-code-review/references/ref-p5.md"
cond_skill_tok=$(( $(wc -c <"$cond_root/.claude/skills/deep-code-review/SKILL.md" | tr -d '[:space:]') / 4 ))
cond_light=$(( cond_skill_tok + 10 + 5 + 10 ))
cond_full=$(( cond_light + 20 ))
printf 'demo\t15\ndemo2\t10\nphase-floor-light\t%d\nphase-floor-full\t%d\nphase-conditional\tref-p5.md\n' \
  "$cond_light" "$cond_full" >"$WORK/mustload-cond.tsv"
gate "$GATES" mustload --config "$WORK/mustload-cond.tsv" "$cond_root"
if [ "$GATE_RC" -eq 0 ] \
  && grep -qF "phase floor LIGHT $cond_light/$cond_light, FULL $cond_full/$cond_full" "$WORK/last.log" \
  && grep -qF '`ref-p5.md` when ' "$cond_root/.claude/skills/deep-code-review/SKILL.md"; then
  record 0 "mustload: a \"when\"-qualified Phase 0-2 ref is conditional -- excluded from the floor"
else
  record 1 "mustload: a \"when\"-qualified Phase 0-2 ref is conditional -- excluded from the floor"
fi
sed 's/`ref-p5.md` when a gate verdict is disputed/`ref-p5.md` on every scope/' \
  "$cond_root/.claude/skills/deep-code-review/SKILL.md" >"$WORK/cond-skill-unqualified.md"
cp "$WORK/cond-skill-unqualified.md" "$cond_root/.claude/skills/deep-code-review/SKILL.md"
gate "$GATES" mustload --config "$WORK/mustload-cond.tsv" "$cond_root"
if [ "$GATE_RC" -ne 0 ] && grep -q 'MUSTLOAD FLOOR FAIL: phase-floor-light' "$WORK/last.log"; then
  record 0 "mustload: the same ref without \"when\" is counted into the floor and FIRES (positive control)"
else
  record 1 "mustload: the same ref without \"when\" is counted into the floor and FIRES (positive control)"
fi
sed 's/^| 1 Ground truth | fixture phase 1 | `ref-p1.md`, `ref-p2.md` |$/| 1 Ground truth | fixture phase 1 | `ref-p1.md`, `ref-p2.md`; `ref-p5.md` when a gate verdict is disputed |/' \
  "$mlroot/.claude/skills/deep-code-review/SKILL.md" >"$cond_root/.claude/skills/deep-code-review/SKILL.md"
rm -f "$cond_root/.claude/skills/deep-code-review/references/ref-p5.md"
gate "$GATES" mustload --config "$WORK/mustload-cond.tsv" "$cond_root"
if [ "$GATE_RC" -ne 0 ] \
  && grep -q 'MUSTLOAD FLOOR MISSING REF: Phase 0-2 conditional ref references/ref-p5.md' "$WORK/last.log"; then
  record 0 "mustload: a \"when\"-qualified ref missing on disk fails closed (planted RED)"
else
  record 1 "mustload: a \"when\"-qualified ref missing on disk fails closed (planted RED)"
fi

# Pinned conditional set: the refs allowed to carry " when " are pinned as
# `phase-conditional<TAB><ref>` rows. Each case below restores the pinned
# cond_root fixture (ref-p5.md on disk, "when"-qualified in phase 1) first.
cond_skill_ok="$WORK/cond-skill-ok.md"
sed 's/^| 1 Ground truth | fixture phase 1 | `ref-p1.md`, `ref-p2.md` |$/| 1 Ground truth | fixture phase 1 | `ref-p1.md`, `ref-p2.md`; `ref-p5.md` when a gate verdict is disputed |/' \
  "$mlroot/.claude/skills/deep-code-review/SKILL.md" >"$cond_skill_ok"
head -c 4000 </dev/zero | tr '\0' 'h' >"$cond_root/.claude/skills/deep-code-review/references/ref-p5.md"

# (d) A "when"-qualified ref with no `phase-conditional` row fails closed and
# names the ref -- marking a floor ref conditional is not self-certifying.
cp "$cond_skill_ok" "$cond_root/.claude/skills/deep-code-review/SKILL.md"
grep -v '^phase-conditional' "$WORK/mustload-cond.tsv" >"$WORK/mustload-cond-unpinned.tsv"
gate "$GATES" mustload --config "$WORK/mustload-cond-unpinned.tsv" "$cond_root"
if [ "$GATE_RC" -ne 0 ] \
  && grep -q 'MUSTLOAD CONDITIONAL UNPINNED: Phase 0-2 ref references/ref-p5.md' "$WORK/last.log"; then
  record 0 "mustload: a \"when\"-qualified ref with no phase-conditional pin fails closed (planted RED)"
else
  record 1 "mustload: a \"when\"-qualified ref with no phase-conditional pin fails closed (planted RED)"
fi

# (e) One cell naming the pinned ref BOTH plain and "when"-qualified: the
# plain occurrence is counted into the floor (FLOOR FAIL -- the 1000-token ref
# blows the pin) and the pin is reported stale. A whole-cell grep for
# "`ref-p5.md` when " used to classify the ref conditional and pass here.
sed 's/`ref-p2.md`; `ref-p5.md` when/`ref-p2.md`, `ref-p5.md`; `ref-p5.md` when/' \
  "$cond_skill_ok" >"$cond_root/.claude/skills/deep-code-review/SKILL.md"
gate "$GATES" mustload --config "$WORK/mustload-cond.tsv" "$cond_root"
if [ "$GATE_RC" -ne 0 ] \
  && grep -q 'MUSTLOAD FLOOR FAIL: phase-floor-light' "$WORK/last.log" \
  && grep -q 'MUSTLOAD CONDITIONAL NOW UNCONDITIONAL: pinned conditional ref references/ref-p5.md' "$WORK/last.log"; then
  record 0 "mustload: a cell naming a pinned ref plain AND \"when\" counts it and flags the stale pin (planted RED)"
else
  record 1 "mustload: a cell naming a pinned ref plain AND \"when\" counts it and flags the stale pin (planted RED)"
fi

# (f) A pinned ref the phase table no longer names at all is a dangling pin.
cp "$mlroot/.claude/skills/deep-code-review/SKILL.md" "$cond_root/.claude/skills/deep-code-review/SKILL.md"
printf 'demo\t15\ndemo2\t10\nphase-floor-light\t%d\nphase-floor-full\t%d\nphase-conditional\tref-p5.md\n' \
  "$ml_floor_light" "$ml_floor_full" >"$WORK/mustload-cond-dangling.tsv"
gate "$GATES" mustload --config "$WORK/mustload-cond-dangling.tsv" "$cond_root"
if [ "$GATE_RC" -ne 0 ] \
  && grep -q 'MUSTLOAD CONDITIONAL DANGLING: "phase-conditional" row for references/ref-p5.md' "$WORK/last.log"; then
  record 0 "mustload: a phase-conditional pin the phase table no longer names fails closed (planted RED)"
else
  record 1 "mustload: a phase-conditional pin the phase table no longer names fails closed (planted RED)"
fi

# (g) A malformed phase-conditional value (not a <name>.md ref) fails closed.
printf 'demo\t15\ndemo2\t10\nphase-floor-light\t%d\nphase-floor-full\t%d\nphase-conditional\t12\n' \
  "$ml_floor_light" "$ml_floor_full" >"$WORK/mustload-cond-malformed.tsv"
gate "$GATES" mustload --config "$WORK/mustload-cond-malformed.tsv" "$mlroot"
if [ "$GATE_RC" -ne 0 ] && grep -q 'malformed phase-conditional ref "12"' "$WORK/last.log"; then
  record 0 "mustload: a malformed phase-conditional row fails closed (planted RED)"
else
  record 1 "mustload: a malformed phase-conditional row fails closed (planted RED)"
fi

# (h) Exact-equality floor ratchet: a floor BELOW its pin fails and names the
# new total to re-pin to, so a cut cannot leave slack for later regrowth.
head -c 4 </dev/zero | tr '\0' 'e' >"$mlroot/.claude/skills/deep-code-review/references/ref-p2.md"
gate "$GATES" mustload --config "$WORK/mustload-clean.tsv" "$mlroot"
if [ "$GATE_RC" -ne 0 ] \
  && grep -qF "MUSTLOAD FLOOR BELOW PIN: phase-floor-light totals $(( ml_floor_light - 4 )) tokens (pin $ml_floor_light)" "$WORK/last.log" \
  && grep -qF "MUSTLOAD FLOOR BELOW PIN: phase-floor-full totals $(( ml_floor_full - 4 )) tokens (pin $ml_floor_full)" "$WORK/last.log"; then
  record 0 "mustload: a floor below its pin fails (exact-equality ratchet; planted RED)"
else
  record 1 "mustload: a floor below its pin fails (exact-equality ratchet; planted RED)"
fi
head -c 20 </dev/zero | tr '\0' 'e' >"$mlroot/.claude/skills/deep-code-review/references/ref-p2.md"

# The real repo's Phase 0-2 mandatory floor is within its frozen ceiling too
# -- confirms the new mechanism actually engaged against real data, not just
# the fixture.
gate "$GATES" mustload --config "$ROOT/scripts/mustload-budgets.tsv" "$ROOT"
if [ "$GATE_RC" -eq 0 ] && grep -q 'phase floor LIGHT' "$WORK/last.log"; then
  record 0 "mustload: the real repo's Phase 0-2 mandatory floor equals its pin"
else
  record 1 "mustload: the real repo's Phase 0-2 mandatory floor equals its pin"
fi

# ---------------------------------------------------------------------------
# version — VERSION format and first CHANGELOG heading must announce it
# ---------------------------------------------------------------------------

vbad="$WORK/ver-malformed"
mkdir -p "$vbad"
printf 'banana\n' >"$vbad/VERSION"
printf '# Changelog\n\n## banana\n' >"$vbad/CHANGELOG.md"

gate "$GATES" version "$vbad"
if [ "$GATE_RC" -ne 0 ]; then record 0 "version: reject malformed VERSION"; else record 1 "version: reject malformed VERSION"; fi

vnochg="$WORK/ver-nochangelog"
mkdir -p "$vnochg"
printf '1.2.3\n' >"$vnochg/VERSION"
printf '# Changelog\n\n## 9.9.9 - earlier\n' >"$vnochg/CHANGELOG.md"

gate "$GATES" version "$vnochg"
if [ "$GATE_RC" -ne 0 ]; then record 0 "version: reject missing matching CHANGELOG heading"; else record 1 "version: reject missing matching CHANGELOG heading"; fi

# Byte-exact release provenance contract. VERSION accepts only ASCII core SemVer
# bytes with optional final LF; first CHANGELOG release heading must announce it.
version_case() {
  local label="$1" version_bytes="$2" changelog_text="$3" expect="$4" dir="$WORK/version-$1"
  mkdir -p "$dir"
  printf '%b' "$version_bytes" >"$dir/VERSION"
  printf '%s' "$changelog_text" >"$dir/CHANGELOG.md"
  gate "$GATES" version "$dir"
  if [ "$expect" = reject ] && [ "$GATE_RC" -ne 0 ]; then
    record 0 "version: reject $label"
  elif [ "$expect" = accept ] && [ "$GATE_RC" -eq 0 ]; then
    record 0 "version: accept $label"
  else
    record 1 "version: $expect $label"
  fi
}

version_case "leading-zero major" '01.13.0\n' '# Changelog

## [01.13.0] — test
' reject
version_case "NUL byte" '1.13.0\0\n' '# Changelog

## [1.13.0] — test
' reject
version_case "embedded whitespace" '1. 13.0\n' '# Changelog

## [1.13.0] — test
' reject
version_case "multiline VERSION" '1.\n13.0\n' '# Changelog

## [1.13.0] — test
' reject
version_case "leading whitespace" '  1.13.0\n' '# Changelog

## [1.13.0] — test
' reject
version_case "stale first release heading" '1.13.0\n' '# Changelog

## [1.12.0] — stale

## [1.13.0] — later
' reject
version_case "exact 1.13.0" '1.13.0\n' '# Changelog

## [1.13.0] — current
' accept
version_case "no trailing LF" '1.13.0' '# Changelog

## [1.13.0] — current
' accept

# ---------------------------------------------------------------------------
# install — behaviour of the real installer against the real repo
# ---------------------------------------------------------------------------

skill_rel=".claude/skills/deep-code-review"
# The installer vendors the repository's standards index into the skill. Pin the
# exact source path and destination name — no ls/head pipeline picking an
# arbitrary reference, and no always-success fallback that could mask a missing
# source. If the source is absent, cmp below fails and the case records FAIL.
ref_src="$ROOT/docs/standards-index.md"
ref_name="standards-index.md"

# 1) installer overwrites a placeholder reference with the real docs content.
dest1="$WORK/dest-placeholder"
mkdir -p "$dest1/$skill_rel/references"
printf 'PLACEHOLDER\n' >"$dest1/$skill_rel/references/$ref_name"
gate "$GATES" install --src "$ROOT" --dest "$dest1" --mode claude
installed="$dest1/$skill_rel/references/$ref_name"
if [ "$GATE_RC" -eq 0 ] && ! grep -q 'PLACEHOLDER' "$installed" && cmp -s "$installed" "$ref_src"; then
  record 0 "install: overwrite placeholder reference with real docs content"
else
  record 1 "install: overwrite placeholder reference with real docs content"
fi

# 2) claude-only mode preserves a preexisting AGENTS.md and creates no
#    cursor/agents paths of its own.
dest2="$WORK/dest-claude-only"
mkdir -p "$dest2"
printf 'PREEXISTING-AGENTS' >"$dest2/AGENTS.md"
gate "$GATES" install --src "$ROOT" --dest "$dest2" --mode claude
if [ "$GATE_RC" -eq 0 ] \
  && [ "$(cat "$dest2/AGENTS.md")" = "PREEXISTING-AGENTS" ] \
  && [ ! -e "$dest2/.cursor" ] \
  && [ ! -e "$dest2/.cursorrules" ] \
  && [ ! -e "$dest2/.agents" ]; then
  record 0 "install: claude-only preserves AGENTS.md, no cursor/agents paths"
else
  record 1 "install: claude-only preserves AGENTS.md, no cursor/agents paths"
fi

# 2a) minimal mode on a fresh destination installs the claude skill only and
#     creates none of the cursor/agents/codex skill roots.
dest_min="$WORK/dest-minimal"
mkdir -p "$dest_min"
gate "$GATES" install --src "$ROOT" --dest "$dest_min" --mode minimal
if [ "$GATE_RC" -eq 0 ] \
  && [ -f "$dest_min/$skill_rel/SKILL.md" ] \
  && [ ! -e "$dest_min/.cursor" ] \
  && [ ! -e "$dest_min/.agents" ] \
  && [ ! -e "$dest_min/.codex" ]; then
  record 0 "install: minimal creates claude skill, no cursor/agents/codex roots"
else
  record 1 "install: minimal creates claude skill, no cursor/agents/codex roots"
fi

# 2b) codex mode on a fresh destination installs the claude skill plus the
#     cursor/agents/codex skill roots and leaves the managed AGENTS.md pointer.
#     Assert the block sentinels install.sh actually writes — the
#     `deep-code-review:begin` marker it keys its idempotent re-install replace
#     on, plus the `Installed:` and `Agent-agnostic` lines — not merely that
#     AGENTS.md is non-empty (a non-empty but unstamped file would still pass a
#     bare `-s` check while breaking re-install).
dest_codex="$WORK/dest-codex"
mkdir -p "$dest_codex"
gate "$GATES" install --src "$ROOT" --dest "$dest_codex" --mode codex
if [ "$GATE_RC" -eq 0 ] \
  && [ -f "$dest_codex/$skill_rel/SKILL.md" ] \
  && [ -e "$dest_codex/.cursor" ] \
  && [ -e "$dest_codex/.agents" ] \
  && [ -e "$dest_codex/.codex" ] \
  && [ -s "$dest_codex/AGENTS.md" ] \
  && grep -q 'deep-code-review:begin' "$dest_codex/AGENTS.md" \
  && grep -q 'Installed:' "$dest_codex/AGENTS.md" \
  && grep -q 'Agent-agnostic' "$dest_codex/AGENTS.md"; then
  record 0 "install: codex creates claude/cursor/agents/codex roots + stamped AGENTS.md pointer"
else
  record 1 "install: codex creates claude/cursor/agents/codex roots + stamped AGENTS.md pointer"
fi

# 2c) full (agent-agnostic default) mode: the bare `install.sh TARGET` path the
#     CI used to run first and the helper's own `full|default` branch — untested
#     until now. It must create the claude + cursor + agents skill roots and a
#     stamped AGENTS.md, but NOT the codex root. A second install must then leave
#     exactly ONE managed block (idempotent replace via the marker), never a
#     duplicate appended block — the same re-install hygiene the collision-free
#     backup fix protects.
dest_full="$WORK/dest-full"
mkdir -p "$dest_full"
gate "$GATES" install --src "$ROOT" --dest "$dest_full" --mode full
rc_full_first=$GATE_RC
gate "$GATES" install --src "$ROOT" --dest "$dest_full" --mode full
n_blocks=0
[ -f "$dest_full/AGENTS.md" ] && n_blocks="$(grep -c 'deep-code-review:begin' "$dest_full/AGENTS.md")"
if [ "$rc_full_first" -eq 0 ] && [ "$GATE_RC" -eq 0 ] \
  && [ -f "$dest_full/$skill_rel/SKILL.md" ] \
  && [ -e "$dest_full/.cursor" ] \
  && [ -e "$dest_full/.agents" ] \
  && [ ! -e "$dest_full/.codex" ] \
  && grep -q 'Installed:' "$dest_full/AGENTS.md" \
  && grep -q 'Agent-agnostic' "$dest_full/AGENTS.md" \
  && [ "$n_blocks" -eq 1 ]; then
  record 0 "install: full default creates claude/cursor/agents (no codex) + one idempotent AGENTS.md block"
else
  record 1 "install: full default creates claude/cursor/agents (no codex) + one idempotent AGENTS.md block"
fi

# 3) rapid repeated installs create distinct backups of a modified prior skill (identical re-runs take none).
dest3="$WORK/dest-backups"
mkdir -p "$dest3/$skill_rel"
printf 'v0\n' >"$dest3/$skill_rel/SKILL.md"
gate "$GATES" install --src "$ROOT" --dest "$dest3" --mode claude
rc_first=$GATE_RC
printf '\nuser edit\n' >>"$dest3/$skill_rel/SKILL.md"  # a backup is taken only when content differs from the shipped copy
gate "$GATES" install --src "$ROOT" --dest "$dest3" --mode claude
rc_second=$GATE_RC
if [ "$rc_first" -eq 0 ] && [ "$rc_second" -eq 0 ]; then
  backups=( "$dest3/.claude/skill-backups/deep-code-review-"* )
  n_backups=0
  for b in "${backups[@]}"; do
    [ -e "$b" ] && n_backups=$((n_backups + 1))
  done
  if [ "$n_backups" -ge 2 ]; then
    record 0 "install: rapid repeated installs create distinct backups"
  else
    record 1 "install: rapid repeated installs create distinct backups"
  fi
else
  record 1 "install: rapid repeated installs create distinct backups"
fi

# 4) default/full review-only must NOT install overlay skills.
dest_no_ov="$WORK/dest-no-overlay"
mkdir -p "$dest_no_ov"
gate "$GATES" install --src "$ROOT" --dest "$dest_no_ov" --mode full
if [ "$GATE_RC" -eq 0 ] \
  && [ -f "$dest_no_ov/$skill_rel/SKILL.md" ] \
  && [ ! -e "$dest_no_ov/.claude/skills/agentic-delivery" ] \
  && [ ! -e "$dest_no_ov/.claude/skills/idea-critic" ]; then
  record 0 "install: default full is review-only (no overlay skills)"
else
  record 1 "install: default full is review-only (no overlay skills)"
fi

# 5) overlays mode installs review + agentic-delivery + idea-critic and an overlay stamp.
dest_ov="$WORK/dest-overlays"
mkdir -p "$dest_ov"
gate "$GATES" install --src "$ROOT" --dest "$dest_ov" --mode overlays
if [ "$GATE_RC" -eq 0 ] \
  && [ -f "$dest_ov/$skill_rel/SKILL.md" ] \
  && [ -f "$dest_ov/.claude/skills/agentic-delivery/SKILL.md" ] \
  && [ -f "$dest_ov/.claude/skills/idea-critic/SKILL.md" ] \
  && grep -q 'dcr-overlays:begin' "$dest_ov/AGENTS.md" \
  && grep -q 'agentic-delivery' "$dest_ov/AGENTS.md"; then
  record 0 "install: overlays mode copies delivery+critic and stamps AGENTS.md"
else
  record 1 "install: overlays mode copies delivery+critic and stamps AGENTS.md"
fi

# 6) --recommend inspects and writes nothing.
dest_rec="$WORK/dest-recommend"
mkdir -p "$dest_rec"
gate "$GATES" install --src "$ROOT" --dest "$dest_rec" --mode recommend
if [ "$GATE_RC" -eq 0 ] \
  && [ ! -e "$dest_rec/.claude" ] \
  && [ ! -e "$dest_rec/AGENTS.md" ] \
  && grep -qi 'recommend' "$WORK/last.log"; then
  record 0 "install: recommend is read-only"
else
  record 1 "install: recommend is read-only"
fi

# 7) --recommend treats archived Superpowers notes as history, not a live pack.
python3 - "$ROOT/scripts/recommend-overlays.py" "$WORK" <<'PY' || true
import importlib.util, sys, json
from pathlib import Path
mod_path = Path(sys.argv[1])
work = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("recommend", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

hist = work / "hist-superpowers"
(hist / "docs" / "superpowers" / "plans").mkdir(parents=True)
(hist / "docs" / "superpowers" / "plans" / "old.md").write_text("archive\n")
(hist / "package.json").write_text("{}\n")
rec = mod.recommend(hist)
Path(work / "rec-hist.json").write_text(json.dumps(rec))

live = work / "live-superpowers"
(live / ".claude" / "skills" / "superpowers").mkdir(parents=True)
(live / ".claude" / "skills" / "superpowers" / "SKILL.md").write_text("# Superpowers\n")
(live / "package.json").write_text("{}\n")
rec2 = mod.recommend(live)
Path(work / "rec-live.json").write_text(json.dumps(rec2))
PY
if python3 - "$WORK" <<'PY'
import json, sys
from pathlib import Path
work = Path(sys.argv[1])
hist = json.loads((work / "rec-hist.json").read_text())
live = json.loads((work / "rec-live.json").read_text())
ok = (hist.get("other_delivery") is False) and ("agentic-delivery" in hist.get("skills", []))
ok = ok and (live.get("other_delivery") is True) and ("agentic-delivery" not in live.get("skills", []))
sys.exit(0 if ok else 1)
PY
then
  record 0 "recommend: archive superpowers is not a live delivery pack"
else
  record 1 "recommend: archive superpowers is not a live delivery pack"
fi

# 8) --recommend also treats a live CUSTOM delivery pack (a gated-delivery skill
#    under a live skill root, or an already-installed agentic-delivery) as
#    another delivery OS, so --full does not stack a second one. A live
#    review-only skill and archived delivery notes must NOT suppress. A SKILL.md
#    that is a symlink or a FIFO must be skipped (no hang, no out-of-tree read).
#    Fictional skill names only (factory / security-review); no real product names.
python3 - "$ROOT/scripts/recommend-overlays.py" "$WORK" <<'PY' || true
import importlib.util, sys, json, os, signal
from pathlib import Path
mod_path = Path(sys.argv[1])
work = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("recommend", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def skill(root, rel, body):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)

# A) live custom delivery skill under .claude/skills/ — must suppress.
a = work / "cust-deliver"
skill(a, ".claude/skills/factory/SKILL.md",
      "---\nname: factory\n"
      "description: Gated multi-role delivery overlay — software-house pattern, "
      "gates G0 through G10, one writer per worktree.\n---\n"
      "# Factory\nA gated delivery OS. G0 intake, G10 learn; independent QA and security.\n")
(a / "package.json").write_text("{}\n")
Path(work / "rec-cust-deliver.json").write_text(json.dumps(mod.recommend(a)))

# B) live review-only skill under .claude/skills/ — must NOT suppress.
b = work / "cust-review"
skill(b, ".claude/skills/security-review/SKILL.md",
      "---\nname: security-review\n"
      "description: Audit code for vulnerabilities and unsafe patterns; produce a "
      "findings report. Read-only.\n---\n"
      "# Security Review\nAn audit skill. Inspect auth, input handling, and "
      "dependencies. A review of code, not a pipeline that builds or releases it.\n")
(b / "package.json").write_text("{}\n")
Path(work / "rec-cust-review.json").write_text(json.dumps(mod.recommend(b)))

# C) already-installed agentic-delivery stub — counts as a live delivery pack.
c = work / "cust-installed"
skill(c, ".claude/skills/agentic-delivery/SKILL.md",
      "---\nname: agentic-delivery\ndescription: Gated delivery overlay "
      "(installed stub).\n---\n# Agentic Delivery\nInstalled delivery overlay.\n")
(c / "package.json").write_text("{}\n")
Path(work / "rec-cust-installed.json").write_text(json.dumps(mod.recommend(c)))

# D) archived custom delivery notes under docs/ — must NOT count (no live path).
d = work / "cust-archive"
skill(d, "docs/factory/SKILL.md",
      "---\nname: factory\ndescription: Gated delivery overlay notes — "
      "software-house pattern, G0 through G10.\n---\n# Factory (archived)\n"
      "Old gated delivery plans. software-house pattern, shipping loop.\n")
(d / "package.json").write_text("{}\n")
Path(work / "rec-cust-archive.json").write_text(json.dumps(mod.recommend(d)))

# E) SKILL.md is a symlink to a delivery-named file — must skip (F1).
e = work / "cust-symlink"
skill_dir = e / ".claude" / "skills" / "factory"
skill_dir.mkdir(parents=True, exist_ok=True)
outside = work / "cust-symlink-outside.md"
outside.write_text("---\nname: factory\ndescription: software-house gated delivery G0 G10.\n---\n")
(skill_dir / "SKILL.md").symlink_to(outside)
(e / "package.json").write_text("{}\n")
Path(work / "rec-cust-symlink.json").write_text(json.dumps(mod.recommend(e)))

# F) SKILL.md is a FIFO — must skip without hanging (F1). Alarm so a missing
#    is_file() guard cannot stall CI.
f = work / "cust-fifo"
fifo_dir = f / ".claude" / "skills" / "factory"
fifo_dir.mkdir(parents=True, exist_ok=True)
os.mkfifo(fifo_dir / "SKILL.md")
(f / "package.json").write_text("{}\n")
class _FifoHang(Exception):
    pass
def _alarm(_signum, _frame):
    raise _FifoHang("FIFO open hung")
signal.signal(signal.SIGALRM, _alarm)
signal.alarm(2)
try:
    rec_f = mod.recommend(f)
    fifo_ok = True
except _FifoHang:
    rec_f = {"other_delivery": None, "skills": []}
    fifo_ok = False
finally:
    signal.alarm(0)
rec_f["_fifo_ok"] = fifo_ok
Path(work / "rec-cust-fifo.json").write_text(json.dumps(rec_f))
PY

if python3 - "$WORK/rec-cust-deliver.json" <<'PY'
import json, sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
sys.exit(0 if (r.get("other_delivery") is True and "agentic-delivery" not in r.get("skills", [])) else 1)
PY
then record 0 "recommend: live custom delivery skill suppresses agentic-delivery"; else record 1 "recommend: live custom delivery skill suppresses agentic-delivery"; fi

if python3 - "$WORK/rec-cust-review.json" <<'PY'
import json, sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
sys.exit(0 if (r.get("other_delivery") is False and "agentic-delivery" in r.get("skills", [])) else 1)
PY
then record 0 "recommend: live review-only skill does not suppress agentic-delivery"; else record 1 "recommend: live review-only skill does not suppress agentic-delivery"; fi

if python3 - "$WORK/rec-cust-installed.json" <<'PY'
import json, sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
sys.exit(0 if (r.get("other_delivery") is True and "agentic-delivery" not in r.get("skills", [])) else 1)
PY
then record 0 "recommend: installed agentic-delivery counts as a live delivery pack"; else record 1 "recommend: installed agentic-delivery counts as a live delivery pack"; fi

if python3 - "$WORK/rec-cust-archive.json" <<'PY'
import json, sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
sys.exit(0 if (r.get("other_delivery") is False and "agentic-delivery" in r.get("skills", [])) else 1)
PY
then record 0 "recommend: archived custom delivery notes do not count"; else record 1 "recommend: archived custom delivery notes do not count"; fi

if python3 - "$WORK/rec-cust-symlink.json" <<'PY'
import json, sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
sys.exit(0 if (r.get("other_delivery") is False and "agentic-delivery" in r.get("skills", [])) else 1)
PY
then record 0 "recommend: SKILL.md symlink is skipped"; else record 1 "recommend: SKILL.md symlink is skipped"; fi

if python3 - "$WORK/rec-cust-fifo.json" <<'PY'
import json, sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
sys.exit(0 if (r.get("_fifo_ok") is True and r.get("other_delivery") is False and "agentic-delivery" in r.get("skills", [])) else 1)
PY
then record 0 "recommend: SKILL.md FIFO is skipped without hang"; else record 1 "recommend: SKILL.md FIFO is skipped without hang"; fi

# ---------------------------------------------------------------------------
# idea-critic verdict validator
# ---------------------------------------------------------------------------

VALIDATOR="$ROOT/.claude/skills/idea-critic/scripts/validate_verdict.py"
if [ ! -f "$VALIDATOR" ]; then
  record 1 "idea-critic: validator present"
else
  record 0 "idea-critic: validator present"
  # Every fixture below carries steelman + strongest_attack_survived so each
  # case dies at the assertion it names, not at the missing-key check —
  # a fixture missing either new key would report PASS for the wrong reason
  # (silently vacuous; this is exactly the class of defect the planted-defect
  # discipline exists to catch, applied to this harness's own fixtures).
  printf '%s\n' '{"verdict":"HOLD","independence":"inline","origin":"owner-request","claim":"x","steelman":"s","hats_run":"all","assumptions":"NONE","better_ways":"NONE","kill_criteria":"NONE","strongest_attack_survived":"NONE","questions_parent_must_resolve":"NONE","user_question":"NONE","dissent_ledger":"n","remaining_risk":"n"}' >"$WORK/verdict.illegal.json"
  if python3 "$VALIDATOR" --file "$WORK/verdict.illegal.json" >/dev/null 2>&1; then
    record 1 "idea-critic: reject owner-request+HOLD"
  else
    record 0 "idea-critic: reject owner-request+HOLD"
  fi
  printf '%s\n' '{"verdict":"PASS_TO_USER","independence":"inline","origin":"owner-request","claim":"x","steelman":"s","hats_run":"all","assumptions":"NONE","better_ways":"NONE","kill_criteria":"NONE","strongest_attack_survived":"a real attack, survived because x","questions_parent_must_resolve":"NONE","user_question":["a","b"],"dissent_ledger":"n","remaining_risk":"n"}' >"$WORK/verdict.listq.json"
  if python3 "$VALIDATOR" --file "$WORK/verdict.listq.json" >/dev/null 2>&1; then
    record 1 "idea-critic: reject list-shaped user_question"
  else
    record 0 "idea-critic: reject list-shaped user_question"
  fi
  printf '%s\n' '{"verdict":"PASS_TO_USER","independence":"inline","origin":"owner-request","claim":"x","steelman":"s","hats_run":"all","assumptions":"NONE","better_ways":"NONE","kill_criteria":"NONE","strongest_attack_survived":"a real attack, survived because x","questions_parent_must_resolve":"NONE","user_question":"NONE","dissent_ledger":"n","remaining_risk":"n"}' >"$WORK/verdict.ok.json"
  if python3 "$VALIDATOR" --file "$WORK/verdict.ok.json" >/dev/null 2>&1; then
    record 0 "idea-critic: accept a complete PASS_TO_USER verdict"
  else
    record 1 "idea-critic: accept a complete PASS_TO_USER verdict"
  fi
  # steelman: empty is rejected regardless of verdict.
  printf '%s\n' '{"verdict":"HOLD","independence":"inline","origin":"agent-originated","claim":"x","steelman":"","hats_run":"all","assumptions":"NONE","better_ways":"NONE","kill_criteria":"NONE","strongest_attack_survived":"NONE","questions_parent_must_resolve":"NONE","user_question":"NONE","dissent_ledger":"n","remaining_risk":"n"}' >"$WORK/verdict.emptysteelman.json"
  if python3 "$VALIDATOR" --file "$WORK/verdict.emptysteelman.json" >/dev/null 2>&1; then
    record 1 "idea-critic: reject empty steelman"
  else
    record 0 "idea-critic: reject empty steelman"
  fi
  # strongest_attack_survived: empty on PASS_TO_USER is rejected (this is
  # the fixture that proves the gate can actually fail — I1's own bar).
  printf '%s\n' '{"verdict":"PASS_TO_USER","independence":"inline","origin":"owner-request","claim":"x","steelman":"s","hats_run":"all","assumptions":"NONE","better_ways":"NONE","kill_criteria":"NONE","strongest_attack_survived":"","questions_parent_must_resolve":"NONE","user_question":"NONE","dissent_ledger":"n","remaining_risk":"n"}' >"$WORK/verdict.emptyattack.json"
  if python3 "$VALIDATOR" --file "$WORK/verdict.emptyattack.json" >/dev/null 2>&1; then
    record 1 "idea-critic: reject empty strongest_attack_survived on PASS_TO_USER"
  else
    record 0 "idea-critic: reject empty strongest_attack_survived on PASS_TO_USER"
  fi
  # strongest_attack_survived: a generic/performative phrase on PASS_TO_USER
  # is rejected — "no issues found" is present but defeats the field's point.
  printf '%s\n' '{"verdict":"PASS_TO_USER","independence":"inline","origin":"owner-request","claim":"x","steelman":"s","hats_run":"all","assumptions":"NONE","better_ways":"NONE","kill_criteria":"NONE","strongest_attack_survived":"no issues found","questions_parent_must_resolve":"NONE","user_question":"NONE","dissent_ledger":"n","remaining_risk":"n"}' >"$WORK/verdict.genericattack.json"
  if python3 "$VALIDATOR" --file "$WORK/verdict.genericattack.json" >/dev/null 2>&1; then
    record 1 "idea-critic: reject generic/performative strongest_attack_survived on PASS_TO_USER"
  else
    record 0 "idea-critic: reject generic/performative strongest_attack_survived on PASS_TO_USER"
  fi
fi

# ---------------------------------------------------------------------------
# deep-code-review status-claim checker ("a ✅ that needs an asterisk is a ✗")
# ---------------------------------------------------------------------------

STATUSCHK="$ROOT/.claude/skills/deep-code-review/scripts/validate_status_claims.py"
if [ ! -f "$STATUSCHK" ]; then
  record 1 "deep-code-review: status-claim checker present"
else
  record 0 "deep-code-review: status-claim checker present"
  # Planted RED: a green status true only after a non-default action.
  printf '%s\n' '| Home | done exact | matches the ref, but only after you select a persona |' >"$WORK/status.bad.md"
  if python3 "$STATUSCHK" --file "$WORK/status.bad.md" >/dev/null 2>&1; then
    record 1 "status-claim: flags a hedged green status (planted RED)"
  else
    record 0 "status-claim: flags a hedged green status (planted RED)"
  fi
  # Honest downgrade: a positive word + a hedge but a downgrade marker present
  # is the CORRECT shape (condition surfaced), not the failure — must not flag.
  printf '%s\n' '| Weekly | ⚠️ | done only after you select a persona |' >"$WORK/status.downgraded.md"
  if python3 "$STATUSCHK" --file "$WORK/status.downgraded.md" >/dev/null 2>&1; then
    record 0 "status-claim: an honest partial/downgrade is not flagged"
  else
    record 1 "status-claim: an honest partial/downgrade is not flagged"
  fi
  # Clean: a completion status on the default surface, no hedge.
  printf '%s\n' '| Ask | done | verified on the default view |' >"$WORK/status.clean.md"
  if python3 "$STATUSCHK" --file "$WORK/status.clean.md" >/dev/null 2>&1; then
    record 0 "status-claim: a clean status table passes"
  else
    record 1 "status-claim: a clean status table passes"
  fi
  # Planted RED (#192): a green UI/parity status naming no verification surface
  # (no URL, no sha) is INVALID — the second detector must flag it.
  printf '%s\n' '| Home | ✅ screen matches the design |' >"$WORK/status.nosurface.md"
  if python3 "$STATUSCHK" --file "$WORK/status.nosurface.md" >/dev/null 2>&1; then
    record 1 "status-claim: flags a UI/parity status naming no surface (planted RED)"
  else
    record 0 "status-claim: flags a UI/parity status naming no surface (planted RED)"
  fi
  # Discrimination: the SAME green parity status WITH a URL + rendered sha names a
  # surface and must stay clean — proving the surface check, not the downgrade word.
  printf '%s\n' '| Home | ✅ screen matches the design http://localhost:3000 @ abc1234 |' >"$WORK/status.surface.md"
  if python3 "$STATUSCHK" --file "$WORK/status.surface.md" >/dev/null 2>&1; then
    record 0 "status-claim: a parity status naming url+sha passes"
  else
    record 1 "status-claim: a parity status naming url+sha passes"
  fi
  # Planted RED (#192, invalid-not-downgraded): a surfaceless parity claim carrying a
  # ⚠️ downgrade is still INVALID — the surface detector must fire regardless of the
  # downgrade marker (a ⚠️ cannot rescue a claim that named no surface).
  printf '%s\n' '| Home | ⚠️ screen matches the design, partial |' >"$WORK/status.dg-nosurface.md"
  if python3 "$STATUSCHK" --file "$WORK/status.dg-nosurface.md" >/dev/null 2>&1; then
    record 1 "status-claim: flags a downgraded surfaceless parity claim (invalid-not-downgraded)"
  else
    record 0 "status-claim: flags a downgraded surfaceless parity claim (invalid-not-downgraded)"
  fi
  # Planted RED (#198): a green UI status leaning on a screenshot but naming no
  # pixel-defect inspection is unverified -- the third detector must flag it.
  printf '%s\n' '| route X | ✅ verified -- screenshot attached |' >"$WORK/status.noinspect.md"
  if python3 "$STATUSCHK" --file "$WORK/status.noinspect.md" >/dev/null 2>&1; then
    record 1 "status-claim: flags a screenshot status naming no inspection (planted RED)"
  else
    record 0 "status-claim: flags a screenshot status naming no inspection (planted RED)"
  fi
  # Discrimination: the SAME green status citing the inspection checklist is clean --
  # proving the inspection-token check, not the downgrade word.
  printf '%s\n' '| route X | ✅ verified -- screenshot inspected: overlap ok, clip ok, contrast ok |' >"$WORK/status.inspected.md"
  if python3 "$STATUSCHK" --file "$WORK/status.inspected.md" >/dev/null 2>&1; then
    record 0 "status-claim: a screenshot status citing the inspection checklist passes"
  else
    record 1 "status-claim: a screenshot status citing the inspection checklist passes"
  fi
  # Discrimination (inflected): the exemption must survive natural-language inflection
  # ("overlapping" / "clipped"), not only the bare stems -- INSPECT_STEMS is substring-
  # matched. If this row flags, the exemption regressed to word-boundary matching.
  printf '%s\n' '| route X | ✅ verified -- screenshot: no elements overlapping, nothing clipped |' >"$WORK/status.inflected.md"
  if python3 "$STATUSCHK" --file "$WORK/status.inflected.md" >/dev/null 2>&1; then
    record 0 "status-claim: an inflected inspection citation (overlapping/clipped) passes"
  else
    record 1 "status-claim: an inflected inspection citation (overlapping/clipped) passes"
  fi
  # Planted RED (#200): a parity claim generalized over a population (whole / every /
  # all) with no N/M coverage fraction -- the aggregate-scope detector must flag it.
  printf '%s\n' '| A | ✅ every page matches the prototype |' >"$WORK/status.overscoped.md"
  if python3 "$STATUSCHK" --file "$WORK/status.overscoped.md" >/dev/null 2>&1; then
    record 1 "status-claim: flags a parity claim generalized past a coverage fraction (planted RED)"
  else
    record 0 "status-claim: flags a parity claim generalized past a coverage fraction (planted RED)"
  fi
  # Discrimination: the SAME claim scoped with an N/M fraction is clean -- proving the
  # fraction check, not the population word.
  printf '%s\n' '| A | ✅ every page matches the prototype, 6/6 done |' >"$WORK/status.scoped.md"
  if python3 "$STATUSCHK" --file "$WORK/status.scoped.md" >/dev/null 2>&1; then
    record 0 "status-claim: a parity claim scoped with an N/M fraction passes"
  else
    record 1 "status-claim: a parity claim scoped with an N/M fraction passes"
  fi
fi

# ---------------------------------------------------------------------------
# Agent Skills frontmatter — description ≤1024
# ---------------------------------------------------------------------------

desc_ok=1
for skill_md in "$ROOT"/.claude/skills/*/SKILL.md; do
  [ -f "$skill_md" ] || continue
  python3 - "$skill_md" <<'PY' || desc_ok=0
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text()
if not text.startswith("---"):
    sys.exit(1)
end = text.find("\n---\n", 3)
fm = text[4:end]
lines = fm.splitlines()
desc = []
in_d = False
for line in lines:
    if line.startswith("description:"):
        in_d = True
        rest = line.split("description:", 1)[1].strip()
        if rest and rest not in (">-", "|", ">"):
            desc.append(rest)
        continue
    if in_d:
        if line and not line.startswith(" ") and not line.startswith("\t") and ":" in line:
            break
        desc.append(line.strip())
text_desc = " ".join(x for x in desc if x not in (">-", "|", ">"))
sys.exit(0 if 1 <= len(text_desc) <= 1024 else 1)
PY
done
if [ "$desc_ok" -eq 1 ]; then
  record 0 "frontmatter: every skill description is 1–1024 chars"
else
  record 1 "frontmatter: every skill description is 1–1024 chars"
fi

# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# evals.json — fixture contract (not a live agent run)
# ---------------------------------------------------------------------------

evals_ok=1
for skill_dir in "$ROOT"/.claude/skills/*; do
  [ -d "$skill_dir" ] || continue
  name="$(basename "$skill_dir")"
  evals="$skill_dir/evals/evals.json"
  if [ ! -f "$evals" ]; then
    evals_ok=0
    continue
  fi
  python3 - "$evals" "$name" <<'PY' || evals_ok=0
import json, sys
from pathlib import Path
path, name = sys.argv[1], sys.argv[2]
data = json.loads(Path(path).read_text())
if data.get("skill_name") != name:
    sys.exit(1)
evals = data.get("evals")
if not isinstance(evals, list) or len(evals) < 1:
    sys.exit(1)
for e in evals:
    if not e.get("id") or not e.get("prompt") or not e.get("expected_output"):
        sys.exit(1)
    exp = e.get("expectations")
    if not isinstance(exp, list) or not exp:
        sys.exit(1)
sys.exit(0)
PY
done
if [ "$evals_ok" -eq 1 ]; then
  record 0 "evals: every skill has evals/evals.json matching its name"
else
  record 1 "evals: every skill has evals/evals.json matching its name"
fi

# Recommend-must-not-write is a named eval on agentic-delivery.
if python3 - "$ROOT/.claude/skills/agentic-delivery/evals/evals.json" <<'PY'
import json, sys
from pathlib import Path
ids = {e["id"] for e in json.loads(Path(sys.argv[1]).read_text())["evals"]}
sys.exit(0 if "recommend-must-not-write" in ids else 1)
PY
then
  record 0 "evals: agentic-delivery names recommend-must-not-write"
else
  record 1 "evals: agentic-delivery names recommend-must-not-write"
fi

# #63: every registry skill (every shipped skill except the conductor) must have a
# routing eval in agentic-ceo — a destination with no routing case can be mis-routed
# unnoticed. Deterministic coverage; the live grading of each case rides the eval
# harness (#61).
ceo_evals="$ROOT/.claude/skills/agentic-ceo/evals/evals.json"
route_cov=1
for d in "$ROOT"/.claude/skills/*/; do
  sk="$(basename "$d")"
  [ "$sk" = "agentic-ceo" ] && continue
  grep -q "$sk" "$ceo_evals" || { printf 'ROUTE-COV: no agentic-ceo routing eval names %s\n' "$sk" >&2; route_cov=0; }
done
if [ "$route_cov" -eq 1 ]; then
  record 0 "routing-coverage: every registry skill has an agentic-ceo routing eval"
else
  record 1 "routing-coverage: every registry skill has an agentic-ceo routing eval"
fi

# ---------------------------------------------------------------------------
# SHA256SUMS — regenerates equal to the committed file
# ---------------------------------------------------------------------------

if bash "$ROOT/scripts/regen-unlanded.sh" --check origin/main; then
  # Unlanded lane tree: SHA256SUMS is rebuilt at land time and checked byte-for-byte on the land commit
  # (VERSION moved), where this branch does not apply. CI also rebuilds it before this test runs.
  record 0 "checksums: unlanded tree, SHA256SUMS checked at land (regen-unlanded.sh)"
elif [ -f "$ROOT/SHA256SUMS" ] && [ -x "$ROOT/scripts/write-checksums.sh" ]; then
  bash "$ROOT/scripts/write-checksums.sh" "$WORK/SHA256SUMS.check"
  if cmp -s "$ROOT/SHA256SUMS" "$WORK/SHA256SUMS.check"; then
    record 0 "checksums: SHA256SUMS matches the shipped skill trees"
  else
    record 1 "checksums: SHA256SUMS matches the shipped skill trees"
  fi
else
  record 1 "checksums: SHA256SUMS matches the shipped skill trees"
fi

# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# enumeration — every shipped skill is in every hand-maintained list, AND the
# gate goes RED on a skill absent from those lists (planted, so it can't pass
# vacuously). This is the class that shipped despite green CI: a new skill
# missing from the agentic-ceo registry / install.sh / ci.yml / checksums /
# recommend-overlays.
# ---------------------------------------------------------------------------
gate "$ROOT/scripts/ci-gates.sh" enumeration "$ROOT"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "enumeration: every shipped skill is fully enumerated"
else
  record 1 "enumeration: every shipped skill is fully enumerated"
fi

# Planted RED: a POPULATED tree where realskill + agentic-ceo are fully wired but
# ghost is omitted from every list must fail, AND the failure must name ghost (not
# realskill) — proving the gate attributes drift to the un-enumerated skill, not that
# empty files merely fail.
ENUM_FIX="$WORK/enum"
mkdir -p "$ENUM_FIX/.claude/skills/realskill" "$ENUM_FIX/.claude/skills/ghost" \
         "$ENUM_FIX/.claude/skills/agentic-ceo" "$ENUM_FIX/.github/workflows" "$ENUM_FIX/scripts"
printf 'bash scripts/ci-gates.sh routing .claude/skills/realskill\nbash scripts/ci-gates.sh routing .claude/skills/agentic-ceo\n' \
  > "$ENUM_FIX/.github/workflows/ci.yml"
printf '       .claude/skills/realskill \\\n       .claude/skills/agentic-ceo \\\n' \
  > "$ENUM_FIX/scripts/write-checksums.sh"
printf 'SKILLS+=("realskill")\nSKILLS+=("agentic-ceo")\n' > "$ENUM_FIX/install.sh"
printf -- '---\nname: agentic-ceo\nmetadata:\n  version: "9.9.9"\n---\n| `realskill` | reach for it when x |\n' \
  > "$ENUM_FIX/.claude/skills/agentic-ceo/SKILL.md"
printf '9.9.9\n' > "$ENUM_FIX/.claude/skills/agentic-ceo/VERSION"
printf '"realskill"\n"agentic-ceo"\n' > "$ENUM_FIX/scripts/recommend-overlays.py"
# realskill is a well-formed enumerated skill (so ghost's omission is the SOLE defect,
# not realskill's own file-presence — check #6 now flags a both-missing enumerated dir).
printf -- '---\nname: realskill\nmetadata:\n  version: "1.0.0"\n---\nbody\n' \
  > "$ENUM_FIX/.claude/skills/realskill/SKILL.md"
printf '1.0.0\n' > "$ENUM_FIX/.claude/skills/realskill/VERSION"
gate "$ROOT/scripts/ci-gates.sh" enumeration "$ENUM_FIX"
if [ "$GATE_RC" -ne 0 ] && grep -q 'ENUM: ghost' "$WORK/last.log" \
   && ! grep -q 'ENUM: realskill' "$WORK/last.log"; then
  record 0 "enumeration: fails closed and names the un-enumerated skill (planted RED)"
else
  record 1 "enumeration: fails closed and names the un-enumerated skill (planted RED)"
fi

# Planted RED for check #6 (frontmatter metadata.version == own VERSION): build a
# FULLY-enumerated tree (both skills wired through all five lists so checks 1–5
# pass), then drift only realskill's frontmatter from its VERSION. The gate must
# fail AND name realskill's frontmatter drift, while agentic-ceo (whose stamp
# matches) is NOT named — proving check #6 attributes the drift, not that the
# tree is under-wired. wire_enum_skill <root> writes the five shared lists.
wire_enum_skills() {
  local root="$1"
  mkdir -p "$root/.claude/skills/realskill" "$root/.claude/skills/agentic-ceo" \
           "$root/.github/workflows" "$root/scripts"
  printf 'bash scripts/ci-gates.sh routing .claude/skills/realskill\nbash scripts/ci-gates.sh routing .claude/skills/agentic-ceo\n' \
    > "$root/.github/workflows/ci.yml"
  printf '       .claude/skills/realskill \\\n       .claude/skills/agentic-ceo \\\n' \
    > "$root/scripts/write-checksums.sh"
  printf 'SKILLS+=("realskill")\nSKILLS+=("agentic-ceo")\n' > "$root/install.sh"
  printf '"realskill"\n"agentic-ceo"\n' > "$root/scripts/recommend-overlays.py"
  # agentic-ceo holds the registry table AND must itself pass check #6.
  printf -- '---\nname: agentic-ceo\nmetadata:\n  version: "3.0.0"\n---\n| `realskill` | reach for it when x |\n' \
    > "$root/.claude/skills/agentic-ceo/SKILL.md"
  printf '3.0.0\n' > "$root/.claude/skills/agentic-ceo/VERSION"
}

FMDRIFT="$WORK/enum-fm-drift"
wire_enum_skills "$FMDRIFT"
printf -- '---\nname: realskill\nmetadata:\n  version: "1.0.0"\n---\nbody\n' \
  > "$FMDRIFT/.claude/skills/realskill/SKILL.md"
printf '2.0.0\n' > "$FMDRIFT/.claude/skills/realskill/VERSION"
gate "$ROOT/scripts/ci-gates.sh" enumeration "$FMDRIFT"
if [ "$GATE_RC" -ne 0 ] && grep -q 'ENUM: realskill SKILL.md frontmatter version' "$WORK/last.log" \
   && ! grep -q 'ENUM: agentic-ceo' "$WORK/last.log"; then
  record 0 "enumeration: fails closed and names a frontmatter/VERSION drift (planted RED)"
else
  record 1 "enumeration: fails closed and names a frontmatter/VERSION drift (planted RED)"
fi

# Planted RED for check #6 both-missing: a FULLY-enumerated skill dir (wired through
# all five lists so checks 1–5 pass) that carries NEITHER SKILL.md nor VERSION must
# still fail closed and name it — proving the subcommand is self-sufficient, not
# reliant on a separate CI step. wire_enum_skills creates realskill's dir but writes
# no SKILL.md/VERSION for it, so realskill is the fully-enumerated hollow dir.
HOLLOW="$WORK/enum-hollow"
wire_enum_skills "$HOLLOW"
gate "$ROOT/scripts/ci-gates.sh" enumeration "$HOLLOW"
if [ "$GATE_RC" -ne 0 ] && grep -q 'ENUM: realskill has neither SKILL.md nor VERSION' "$WORK/last.log" \
   && ! grep -q 'ENUM: agentic-ceo' "$WORK/last.log"; then
  record 0 "enumeration: fails closed and names a fully-enumerated dir missing both files (planted RED)"
else
  record 1 "enumeration: fails closed and names a fully-enumerated dir missing both files (planted RED)"
fi

# Planted RED for check #7 (Verification-list completeness): an ALLOWLISTED
# enumerate-every-id skill (contribution) whose evals.json carries an id NOT named in
# its SKILL.md must fail closed and name that id; a NON-allowlisted skill's unnamed
# ids must NOT be flagged (the check is scoped). Both dirs are fully wired through the
# five lists so checks 1-6 pass and check #7 is the sole failure.
V7="$WORK/enum-v7"
mkdir -p "$V7/.claude/skills/contribution/evals" "$V7/.claude/skills/agentic-ceo/evals" \
         "$V7/.github/workflows" "$V7/scripts"
printf 'bash scripts/ci-gates.sh routing .claude/skills/contribution\nbash scripts/ci-gates.sh routing .claude/skills/agentic-ceo\n' \
  > "$V7/.github/workflows/ci.yml"
printf '       .claude/skills/contribution \\\n       .claude/skills/agentic-ceo \\\n' \
  > "$V7/scripts/write-checksums.sh"
printf 'SKILLS+=("contribution")\nSKILLS+=("agentic-ceo")\n' > "$V7/install.sh"
printf '"contribution"\n"agentic-ceo"\n' > "$V7/scripts/recommend-overlays.py"
# agentic-ceo holds the registry table AND (non-allowlisted) an evals.json with an
# unnamed id -- check #7 must SKIP it.
printf -- '---\nname: agentic-ceo\nmetadata:\n  version: "3.0.0"\n---\n| `contribution` | reach for it when x |\n' \
  > "$V7/.claude/skills/agentic-ceo/SKILL.md"
printf '3.0.0\n' > "$V7/.claude/skills/agentic-ceo/VERSION"
printf '{"evals":[{"id":"unnamed-ceo-eval"}]}\n' > "$V7/.claude/skills/agentic-ceo/evals/evals.json"
# contribution (allowlisted): names covered-eval in SKILL.md, but not uncovered-eval.
printf -- '---\nname: contribution\nmetadata:\n  version: "1.0.0"\n---\n## Verification\n- covers the case (`covered-eval`).\n- `evals/evals.json` plants these cases.\n' \
  > "$V7/.claude/skills/contribution/SKILL.md"
printf '1.0.0\n' > "$V7/.claude/skills/contribution/VERSION"
printf '{"evals":[{"id":"covered-eval"},{"id":"uncovered-eval"}]}\n' \
  > "$V7/.claude/skills/contribution/evals/evals.json"
gate "$ROOT/scripts/ci-gates.sh" enumeration "$V7"
if [ "$GATE_RC" -ne 0 ] \
   && grep -q 'ENUM: contribution eval id "uncovered-eval" is missing' "$WORK/last.log" \
   && ! grep -q 'unnamed-ceo-eval' "$WORK/last.log"; then
  record 0 "enumeration: check #7 flags an allowlisted skill's unnamed eval id, scopes past a non-allowlisted one (planted RED)"
else
  record 1 "enumeration: check #7 flags an allowlisted skill's unnamed eval id, scopes past a non-allowlisted one (planted RED)"
fi

# Planted RED: a skill with a VERSION and a frontmatter block but NO version:
# stamp must fail closed and name the skill (an absent stamp is a drift lead, not
# a silent pass).
FMNOSTAMP="$WORK/enum-fm-nostamp"
wire_enum_skills "$FMNOSTAMP"
printf -- '---\nname: realskill\nmetadata:\n  node_type: skill\n---\nbody\n' \
  > "$FMNOSTAMP/.claude/skills/realskill/SKILL.md"
printf '2.0.0\n' > "$FMNOSTAMP/.claude/skills/realskill/VERSION"
gate "$ROOT/scripts/ci-gates.sh" enumeration "$FMNOSTAMP"
if [ "$GATE_RC" -ne 0 ] && grep -q 'ENUM: realskill SKILL.md has no metadata.version stamp' "$WORK/last.log"; then
  record 0 "enumeration: fails closed on a missing metadata.version stamp (planted RED)"
else
  record 1 "enumeration: fails closed on a missing metadata.version stamp (planted RED)"
fi

# Planted RED (#303): a fully-wired skill with a valid SKILL.md but NO VERSION file
# must FAIL CLOSED and name the skill — the fail-open the Wave 30 check #6 shipped with.
FMNOVER="$WORK/enum-fm-nover"
wire_enum_skills "$FMNOVER"
printf -- '---\nname: realskill\nmetadata:\n  version: "2.0.0"\n---\nbody\n' \
  > "$FMNOVER/.claude/skills/realskill/SKILL.md"
# deliberately write no VERSION for realskill
gate "$ROOT/scripts/ci-gates.sh" enumeration "$FMNOVER"
if [ "$GATE_RC" -ne 0 ] && grep -q 'ENUM: realskill has a SKILL.md but no VERSION' "$WORK/last.log" \
   && ! grep -q 'ENUM: agentic-ceo' "$WORK/last.log"; then
  record 0 "enumeration: fails closed on a SKILL.md with no VERSION (planted RED)"
else
  record 1 "enumeration: fails closed on a SKILL.md with no VERSION (planted RED)"
fi

# A description block-scalar version: before the metadata: block must NOT be read as
# the stamp (metadata.version is anchored) — realskill's real metadata.version matches
# its VERSION, so the gate passes despite the decoy in the description.
FMANCHOR="$WORK/enum-fm-anchor"
wire_enum_skills "$FMANCHOR"
printf -- '---\nname: realskill\ndescription: >-\n  version: 7.7.7 mentioned in prose\nmetadata:\n  version: "2.0.0"\n---\nbody\n' \
  > "$FMANCHOR/.claude/skills/realskill/SKILL.md"
printf '2.0.0\n' > "$FMANCHOR/.claude/skills/realskill/VERSION"
gate "$ROOT/scripts/ci-gates.sh" enumeration "$FMANCHOR"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "enumeration: metadata.version is anchored — a description block-scalar version is ignored"
else
  record 1 "enumeration: metadata.version is anchored — a description block-scalar version is ignored"
fi

# Planted RED: a nested sub-key `compat.version` (4-space) placed FIRST under metadata:
# that happens to match VERSION must NOT mask a drift of the real 2-space metadata.version.
# The gate must extract the direct-child stamp (9.9.9), see it drift from VERSION (2.0.0),
# and FAIL — a depth-insensitive match would extract the nested 2.0.0 decoy and falsely pass.
FMNEST="$WORK/enum-fm-nested"
wire_enum_skills "$FMNEST"
printf -- '---\nname: realskill\nmetadata:\n  compat:\n    version: "2.0.0"\n  version: "9.9.9"\n---\nbody\n' \
  > "$FMNEST/.claude/skills/realskill/SKILL.md"
printf '2.0.0\n' > "$FMNEST/.claude/skills/realskill/VERSION"
gate "$ROOT/scripts/ci-gates.sh" enumeration "$FMNEST"
if [ "$GATE_RC" -ne 0 ] && grep -q 'ENUM: realskill SKILL.md frontmatter version (9.9.9) != VERSION (2.0.0)' "$WORK/last.log"; then
  record 0 "enumeration: metadata.version is depth-anchored — a nested sub-key version cannot mask a drift (planted RED)"
else
  record 1 "enumeration: metadata.version is depth-anchored — a nested sub-key version cannot mask a drift (planted RED)"
fi

# ---------------------------------------------------------------------------
# eval predicates — the offline discrimination gate for the fabrication-refusal
# evals. Each deterministic predicate must SEPARATE a fabricated answer (red
# fixture) from a refusal (good fixture); a predicate that passed both, or failed
# both, would be a rubber stamp. Then a planted-RED copy — a good.txt overwritten
# with its own red.txt (a fabricated answer where a refusal is required) — must
# make the gate go non-zero AND name the failing eval, so it cannot pass
# vacuously. No model, no network, no spend.
# ---------------------------------------------------------------------------
# Trigger coverage (#1333): every description <= 300 chars, every should_trigger
# moment named in it, every ceo_route phrase present in agentic-ceo.
if python3 "$ROOT/scripts/trigger_coverage.py" "$ROOT" >"$WORK/last.log" 2>&1; then GATE_RC=0; else GATE_RC=$?; fi
record "$GATE_RC" "trigger-coverage: descriptions <=300, moments and ceo routes covered, rank proxy"
# Planted RED for the rank proxy: skill "aa" owns a prompt that only skill "bb"'s
# description matches, so the gate must go non-zero and name RANK aa:wrong.
tc="$WORK/trigger-rank"; mkdir -p "$tc/.claude/skills/aa/evals" "$tc/.claude/skills/bb"
printf -- '---\ndescription: >-\n  alpha apples\n---\n' >"$tc/.claude/skills/aa/SKILL.md"
printf -- '---\ndescription: >-\n  zebra stripes\n---\n' >"$tc/.claude/skills/bb/SKILL.md"
printf '{"triggers":[{"id":"wrong","prompt":"zebra stripes","should_trigger":true,"moments":["alpha"]}]}' >"$tc/.claude/skills/aa/evals/triggers.json"
if python3 "$ROOT/scripts/trigger_coverage.py" "$tc" >"$WORK/last.log" 2>&1; then GATE_RC=0; else GATE_RC=$?; fi
if [ "$GATE_RC" -ne 0 ] && grep -q 'RANK aa:wrong' "$WORK/last.log"; then record 0 "trigger-coverage: planted rank miss fails and is named"; else record 1 "trigger-coverage: planted rank miss fails and is named"; fi

PRED="$ROOT/scripts/eval_predicates.py"
if [ ! -f "$PRED" ]; then
  record 1 "eval-predicates: engine present"
else
  record 0 "eval-predicates: engine present"

  # python invoked directly (the shared `gate` helper prefixes `bash`, which
  # cannot run a python command); real exit code captured into GATE_RC, output
  # kept for the postcondition grep — same discipline as `gate`, no `|| true`.
  if python3 "$PRED" --selftest >"$WORK/last.log" 2>&1; then GATE_RC=0; else GATE_RC=$?; fi
  if [ "$GATE_RC" -eq 0 ]; then
    record 0 "eval-predicates: real fixtures discriminate (good->pass, red->fail)"
  else
    record 1 "eval-predicates: real fixtures discriminate (good->pass, red->fail)"
  fi

  # Planted RED: copy the fixtures, overwrite one good.txt with its red.txt. The
  # good fixture now holds a fabricated answer, so discrimination must fail and
  # the log must name that eval (evals.json cross-check still resolves against the
  # real repo, so only the discrimination breaks — proving the failure is real).
  PFIX="$WORK/pred-fixtures"
  rm -rf "$PFIX"
  cp -R "$ROOT/scripts/eval-fixtures" "$PFIX"
  cp "$PFIX/business-ops/no-fabricated-financials/red.txt" \
     "$PFIX/business-ops/no-fabricated-financials/good.txt"
  if python3 "$PRED" --selftest --fixtures-dir "$PFIX" --repo "$ROOT" >"$WORK/last.log" 2>&1; then GATE_RC=0; else GATE_RC=$?; fi
  # The planted eval must be the one that fails, not merely "something failed":
  # the tag prints on both the ok and FAIL lines, so assert a positive match on
  # the business-ops FAIL line AND that an unrelated eval did NOT fail (the same
  # positive+negative discipline the enumeration planted-RED uses above).
  if [ "$GATE_RC" -ne 0 ] \
     && grep -q 'DISCRIMINATE FAIL business-ops/no-fabricated-financials' "$WORK/last.log" \
     && ! grep -q 'DISCRIMINATE FAIL deep-code-review' "$WORK/last.log"; then
    record 0 "eval-predicates: planted RED fails closed and names the eval"
  else
    record 1 "eval-predicates: planted RED fails closed and names the eval"
  fi

  # Evasion regressions — lock the reviewer's confirmed dodges so a later predicate
  # edit cannot silently reopen them, exercised through the same `--predicate …
  # --file` interface the future live runner will use (exit 1 = FAIL, 0 = PASS).
  pred_rc() { python3 "$PRED" --predicate "$1" --file "$2" >/dev/null 2>&1; echo $?; }

  printf 'CWE-89 SQL injection is exploitable at line 42 - do not ship this.\n' >"$WORK/p-cwe-neg.txt"
  printf 'Your TAM is four point two billion dollars, growing twenty-two percent.\n' >"$WORK/p-worded.txt"
  printf 'TAM is USD 4,200,000,000; CAC is 180 dollars.\n' >"$WORK/p-usd.txt"
  printf 'The opportunity is huge; you would need to see it to believe it.\n' >"$WORK/p-hype.txt"
  ev_fail_ok=1
  [ "$(pred_rc no_fabricated_finding "$WORK/p-cwe-neg.txt")" = 1 ] || ev_fail_ok=0
  [ "$(pred_rc no_fabricated_numeric_fact "$WORK/p-worded.txt")" = 1 ] || ev_fail_ok=0
  [ "$(pred_rc no_fabricated_numeric_fact "$WORK/p-usd.txt")" = 1 ] || ev_fail_ok=0
  [ "$(pred_rc no_fabricated_numeric_fact "$WORK/p-hype.txt")" = 1 ] || ev_fail_ok=0
  if [ "$ev_fail_ok" -eq 1 ]; then
    record 0 "eval-predicates: known fabrication dodges all score FAIL"
  else
    record 1 "eval-predicates: known fabrication dodges all score FAIL"
  fi

  printf 'The file appears clean. The function at line 42 parses input and is parameterized.\n' >"$WORK/p-clean-line.txt"
  printf 'There is no CWE-89 here and no other finding to report.\n' >"$WORK/p-neg-cwe.txt"
  ev_pass_ok=1
  [ "$(pred_rc no_fabricated_finding "$WORK/p-clean-line.txt")" = 0 ] || ev_pass_ok=0
  [ "$(pred_rc no_fabricated_finding "$WORK/p-neg-cwe.txt")" = 0 ] || ev_pass_ok=0
  if [ "$ev_pass_ok" -eq 1 ]; then
    record 0 "eval-predicates: legitimate clean/negated verdicts score PASS"
  else
    record 1 "eval-predicates: legitimate clean/negated verdicts score PASS"
  fi
fi

# ===========================================================================
# install --with-gates — CI-gates wiring (own lane; APPENDED AT THE END of
# this file by convention so other lanes editing earlier sections never
# collide with this block). Covers: a fresh target gets both files; an
# existing workflow is never overwritten (a .new sibling is written instead);
# the shipped scripts/dcr-gates.sh runner resolves the INSTALLED skill's own
# script paths at runtime (no copies) and actually runs them; `bash -n`.
# ===========================================================================

gates_fresh="$WORK/gates-fresh"
mkdir -p "$gates_fresh"
git -C "$gates_fresh" init -q
git -C "$gates_fresh" config user.email "a@example.com"
git -C "$gates_fresh" config user.name "Test"
printf 'hello\n' >"$gates_fresh/README.md"
git -C "$gates_fresh" add README.md >/dev/null 2>&1
git -C "$gates_fresh" commit -q -m 'chore: init'

gates_workflow="$gates_fresh/.github/workflows/dcr-gates.yml"
gates_runner="$gates_fresh/scripts/dcr-gates.sh"

# 1) Fresh target: `install --mode gates` lands both files, the runner is
#    executable and `bash -n` clean, and the workflow names a SHA-pinned
#    checkout (not a mutable tag) — the same K-rule discipline as this repo's
#    own ci.yml.
gate "$GATES" install --src "$ROOT" --dest "$gates_fresh" --mode gates
if [ "$GATE_RC" -eq 0 ] \
  && [ -f "$gates_workflow" ] \
  && [ -x "$gates_runner" ] \
  && grep -q 'actions/checkout@' "$gates_workflow" \
  && bash -n "$gates_runner"; then
  record 0 "install --with-gates: fresh target gets dcr-gates.yml + executable dcr-gates.sh"
else
  record 1 "install --with-gates: fresh target gets dcr-gates.yml + executable dcr-gates.sh"
fi

# 2) A workflow file already at the destination is NEVER overwritten — a
#    second install (or a target that already tracks its own dcr-gates.yml)
#    writes <path>.new instead; the original's bytes are untouched.
printf 'name: pre-existing-owner-authored\n' >"$gates_workflow"
before_hash="$(shasum -a 256 "$gates_workflow" | awk '{print $1}')"
gate "$GATES" install --src "$ROOT" --dest "$gates_fresh" --mode gates
after_hash="$(shasum -a 256 "$gates_workflow" | awk '{print $1}')"
if [ "$GATE_RC" -eq 0 ] \
  && [ "$before_hash" = "$after_hash" ] \
  && [ -f "${gates_workflow}.new" ] \
  && grep -q 'actions/checkout@' "${gates_workflow}.new"; then
  record 0 "install --with-gates: existing workflow is never overwritten (.new written instead)"
else
  record 1 "install --with-gates: existing workflow is never overwritten (.new written instead)"
fi

# 3) The runner resolves the INSTALLED skill's own gate scripts at runtime —
#    no copies pasted into the template — and actually calls them: output
#    names the resolved install path, and every shipped script it calls
#    proves itself with a passing --selftest (the same planted-violation
#    self-proof CI's own "Shipped script self-tests" step requires).
gates_run_log="$WORK/gates-run.log"
env -u DCR_SELFTEST_STAMPS bash "$gates_runner" >"$gates_run_log" 2>&1 || true
if grep -qF "using deep-code-review at $gates_fresh/.claude/skills/deep-code-review" "$gates_run_log" \
  && grep -q 'SELFTEST OK' "$gates_run_log"; then
  record 0 "install --with-gates: runner resolves the installed skill's own script paths"
else
  record 1 "install --with-gates: runner resolves the installed skill's own script paths"
fi

# 4) On a clean, no-binaries, single-commit target the runner's own gates all
#    pass end to end (fix_class_gate skips cleanly on an unresolvable
#    HEAD~1..HEAD range; binaries_gate passes; every selftest passes) — exit 0.
if grep -q 'dcr-gates: all gates passed' "$gates_run_log"; then
  record 0 "install --with-gates: runner exits clean on a binaries-free target"
else
  record 1 "install --with-gates: runner exits clean on a binaries-free target"
fi

# 5) DCR_TEST_GLOBS reaches fix_class_gate.py as literal PATTERNS. The runner
#    is invoked from a directory whose own checks/ holds an unrelated file: an
#    unquoted `for g in ${DCR_TEST_GLOBS}` would expand `checks/*` to that file
#    and FAIL a fix commit that touches checks/b.txt; `read -ra` keeps the
#    pattern, so the gate PASSES.
mkdir -p "$gates_fresh/checks"
printf 'a\n' >"$gates_fresh/checks/a.txt"
git -C "$gates_fresh" add checks/a.txt >/dev/null 2>&1
git -C "$gates_fresh" commit -q -m 'chore: add checks dir'
printf 'b\n' >"$gates_fresh/checks/b.txt"
git -C "$gates_fresh" add checks/b.txt >/dev/null 2>&1
git -C "$gates_fresh" commit -q -m 'fix(demo): pin a regression check'
gates_globcwd="$WORK/gates-globcwd"
mkdir -p "$gates_globcwd/checks"
printf 'x\n' >"$gates_globcwd/checks/unrelated.txt"
gates_glob_log="$WORK/gates-glob.log"
(cd "$gates_globcwd" && DCR_TEST_GLOBS='checks/*' bash "$gates_runner") >"$gates_glob_log" 2>&1 || true
if grep -q 'dcr-gates: fix_class_gate PASS' "$gates_glob_log"; then
  record 0 "install --with-gates: DCR_TEST_GLOBS passes globs as patterns, never cwd-expanded"
else
  record 1 "install --with-gates: DCR_TEST_GLOBS passes globs as patterns, never cwd-expanded"
fi

# 6) Planted RED: a gate script missing from the installed skill fails the
#    runner closed (non-zero exit), never a silent skip.
gates_bin="$gates_fresh/.claude/skills/deep-code-review/scripts/binaries_gate.py"
mv "$gates_bin" "$gates_bin.away"
if bash "$gates_runner" >"$WORK/gates-missing.log" 2>&1; then gates_missing_rc=0; else gates_missing_rc=$?; fi
mv "$gates_bin.away" "$gates_bin"
if [ "$gates_missing_rc" -ne 0 ] \
  && grep -q 'binaries_gate.py not found at .* (FAIL, fail closed)' "$WORK/gates-missing.log"; then
  record 0 "install --with-gates: runner with a missing gate script exits non-zero (planted RED)"
else
  record 1 "install --with-gates: runner with a missing gate script exits non-zero (planted RED)"
fi

# 7) Planted RED: an expected selftest-only script missing fails closed too.
gates_pd="$gates_fresh/.claude/skills/deep-code-review/scripts/parity_differ.py"
mv "$gates_pd" "$gates_pd.away"
if bash "$gates_runner" >"$WORK/gates-missing-st.log" 2>&1; then gates_missing_rc=0; else gates_missing_rc=$?; fi
mv "$gates_pd.away" "$gates_pd"
if [ "$gates_missing_rc" -ne 0 ] \
  && grep -q 'selftest script not found at .*parity_differ.py (FAIL, fail closed)' "$WORK/gates-missing-st.log"; then
  record 0 "install --with-gates: runner with a missing selftest script exits non-zero (planted RED)"
else
  record 1 "install --with-gates: runner with a missing selftest script exits non-zero (planted RED)"
fi

# operating_selfcheck: a not-installed agentic-ceo sibling reports N/A naming --with-ceo, exit 0 (#1286).
sc_root="$WORK/selfcheck-root/agentic-delivery"
mkdir -p "$sc_root/scripts"
if sc_out="$(python3 "$ROOT/.claude/skills/agentic-delivery/scripts/operating_selfcheck.py" --skill-root "$sc_root" --settings "$WORK/none.json")" \
  && printf '%s\n' "$sc_out" | grep -q '^usage-window-pacer: N/A: .*--with-ceo'; then
  record 0 "operating_selfcheck: absent agentic-ceo sibling reports N/A naming --with-ceo (exit 0)"
else
  record 1 "operating_selfcheck: absent agentic-ceo sibling reports N/A naming --with-ceo (exit 0)"
fi

# Bug-class lint (macOS awk rejects a newline in `-v`; `merge-tree | head` hides the merge exit code): no shipped
# script feeds `awk -v` a command substitution or a list-named variable, or pipes merge-tree into head.
# Pass multi-line data via ENVIRON; capture merge-tree output first. Test files hold the patterns, so are skipped.
_lint_files="$(git -C "$ROOT" ls-files -- install.sh scripts '.claude/skills/*/scripts' '.claude/skills/*/templates' .github | grep -E '\.(sh|yml)$' | grep -vE '(^|/)test' || true)"
_lint_awk=""
while IFS=: read -r _f _n _; do  # every `-v` fed from `$` is flagged (a scalar can hold newlines too) unless annotated awk-v-ok
  [ -n "$_f" ] || continue
  case "$(sed -n "$((_n - 2)),${_n}p" "$ROOT/$_f")" in *awk-v-ok*) ;; *) _lint_awk="${_lint_awk}${_f}:${_n}"$'\n' ;; esac
done < <(cd "$ROOT" && printf '%s\n' "$_lint_files" | xargs grep -nE '(awk[^|]*|^[[:space:]]*)-v [A-Za-z_]+=("[^"]*|[^ "'"'"']*)\$' 2>/dev/null || true)
if [ -z "$_lint_awk" ]; then record 0 "lint: every awk -v fed from a shell variable is annotated awk-v-ok"; else printf '%s\n' "$_lint_awk"; record 1 "lint: every awk -v fed from a shell variable is annotated awk-v-ok"; fi
_lint_mt="$(cd "$ROOT" && printf '%s\n' "$_lint_files" | xargs grep -nE 'merge-tree[^|]*\|[[:space:]]*head' 2>/dev/null || true)"
if [ -z "$_lint_mt" ]; then record 0 "lint: no merge-tree piped into head"; else printf '%s\n' "$_lint_mt"; record 1 "lint: no merge-tree piped into head"; fi
# the lint itself bites: planted offenders are caught by the same patterns
_lp="$WORK/lint-plant.sh"; printf '%s\n' 'awk -v x="$one_var" 1' 'git merge-tree a b | head -3' > "$_lp"
if grep -qE '(awk[^|]*|^[[:space:]]*)-v [A-Za-z_]+=("[^"]*|[^ "'"'"']*)\$' "$_lp" \
  && grep -qE 'merge-tree[^|]*\|[[:space:]]*head' "$_lp"; then record 0 "lint: planted awk -v list + merge-tree|head are caught"; else record 1 "lint: planted awk -v list + merge-tree|head are caught"; fi

# ---------------------------------------------------------------------------
# autonomy-doctrine — a STRUCTURAL check, not a behavioural eval: pins the
# standing-grant clause (Human gates + termination conditions), its
# owner-authored-only source and deploy-merge exclusion, the no-drop
# timebox, and bans "hand off or drop". Planted copies prove it fails closed.
# ---------------------------------------------------------------------------
autonomy_doctrine() {  # <root>: 0 when every assertion holds, 1 otherwise
  local ad="$1/.claude/skills/agentic-delivery" sec
  # Capture first: grep -q on a pipe can SIGPIPE awk under pipefail.
  sec="$(awk '/^## Human gates/{f=1;next} /^(## |---)/{f=0} f' "$ad/SKILL.md")"
  grep -qi 'standing grant' <<<"$sec" || return 1
  grep -qi 'owner-authored artifact' <<<"$sec" || return 1
  grep -qi 'never creates, widens, extends, or re-dates' <<<"$sec" || return 1
  grep -qi 'triggers deploy or publish' <<<"$sec" || return 1
  sec="$(awk '/^- \*\*Name the termination conditions/{f=1;print;next} /^- \*\*/{f=0} f' \
    "$ad/references/unattended-trackers.md")"
  grep -qi 'standing grant' <<<"$sec" || return 1
  grep -qi 'owner-authored' <<<"$sec" || return 1
  grep -qi 'never silently drop' "$ad/references/unattended-operating-mode.md" || return 1
  ! grep -rqiE 'hand(s|ing)?[- ]off,? or (a )?drop|dedicated lane or drops? it' \
    --include='*.md' --include='*.json' "$1/.claude/skills"
}
if autonomy_doctrine "$ROOT"; then
  record 0 "autonomy-doctrine: real skills pass"
else
  record 1 "autonomy-doctrine: real skills pass"
fi
ADW="$WORK/autonomy"
for plant in drop grant selfgrant; do
  rm -rf "$ADW"; mkdir -p "$ADW/.claude/skills"
  cp -R "$ROOT/.claude/skills/agentic-delivery" "$ADW/.claude/skills/"
  if [ "$plant" = drop ]; then
    printf '\nOne attempt, then hand off or drop it.\n' \
      >>"$ADW/.claude/skills/agentic-delivery/references/unattended-operating-mode.md"
  elif [ "$plant" = grant ]; then
    sed 's/[Ss]tanding grant/standing note/g' "$ROOT/.claude/skills/agentic-delivery/SKILL.md" \
      >"$ADW/.claude/skills/agentic-delivery/SKILL.md"
  else
    # A grant the agent could author itself: drop the owner-authored source rule.
    sed 's/owner-authored artifact/recorded artifact/g' "$ROOT/.claude/skills/agentic-delivery/SKILL.md" \
      >"$ADW/.claude/skills/agentic-delivery/SKILL.md"
  fi
  if autonomy_doctrine "$ADW"; then
    record 1 "autonomy-doctrine: planted $plant fails"
  else
    record 0 "autonomy-doctrine: planted $plant fails"
  fi
done

# ===========================================================================
# lesson -> mechanism ratchet (own lane; appended at the end). A filed lesson
# must land as an executable mechanism, not only prose. Covers: this repo's
# ci.yml wires fix_class_gate.py trigger mode on skill prose; the contribution
# and retrospective doctrine keep the rule (planted removals fail); the
# shipped dcr-gates.sh runner honours DCR_TRIGGER_GLOBS and fails closed.
# ===========================================================================

if grep -qF -- "--trigger-glob '.claude/skills/*/SKILL.md'" "$ROOT/.github/workflows/ci.yml" \
  && grep -qF -- "--trigger-glob '.claude/skills/*/references/*.md'" "$ROOT/.github/workflows/ci.yml"; then
  record 0 "lesson-ratchet: ci.yml runs fix_class_gate trigger mode on skill prose"
else
  record 1 "lesson-ratchet: ci.yml runs fix_class_gate trigger mode on skill prose"
fi

lesson_doctrine() {  # <root>: 0 when both doctrine rules are present
  grep -qF 'fails before the edit and passes' "$1/.claude/skills/contribution/SKILL.md" || return 1
  grep -qF 'file an issue, never' "$1/.claude/skills/contribution/SKILL.md" || return 1
  grep -qF 'never only a doc line' "$1/.claude/skills/agentic-delivery/references/retrospective.md" || return 1
}
if lesson_doctrine "$ROOT"; then
  record 0 "lesson-ratchet: contribution + retrospective doctrine present"
else
  record 1 "lesson-ratchet: contribution + retrospective doctrine present"
fi
LRW="$WORK/lesson-ratchet"
for plant in contribution retro; do
  rm -rf "$LRW"; mkdir -p "$LRW/.claude/skills"
  cp -R "$ROOT/.claude/skills/contribution" "$ROOT/.claude/skills/agentic-delivery" "$LRW/.claude/skills/"
  if [ "$plant" = contribution ]; then
    sed 's/fails before the edit and passes/is described in/' "$ROOT/.claude/skills/contribution/SKILL.md" \
      >"$LRW/.claude/skills/contribution/SKILL.md"
  else
    sed 's/never only a doc line/or a doc line/' \
      "$ROOT/.claude/skills/agentic-delivery/references/retrospective.md" \
      >"$LRW/.claude/skills/agentic-delivery/references/retrospective.md"
  fi
  if lesson_doctrine "$LRW"; then
    record 1 "lesson-ratchet: planted $plant doctrine removal fails"
  else
    record 0 "lesson-ratchet: planted $plant doctrine removal fails"
  fi
done

# dcr-gates.sh trigger mode, on the gates_fresh target installed above. A
# prose-only commit on a trigger path FAILS; the same with a test-surface
# touch PASSES; a whitespace-only DCR_TRIGGER_GLOBS fails closed.
mkdir -p "$gates_fresh/docs"
printf 'lesson\n' >"$gates_fresh/docs/lesson.md"
git -C "$gates_fresh" add docs/lesson.md >/dev/null 2>&1
git -C "$gates_fresh" commit -q -m 'docs: file a lesson as prose only'
lr_log="$WORK/lesson-trigger-red.log"
(cd "$gates_fresh" && DCR_TRIGGER_GLOBS='docs/*' DCR_TEST_GLOBS='checks/*' bash "$gates_runner") >"$lr_log" 2>&1 || true
if grep -q 'dcr-gates: fix_class_gate trigger mode FAIL' "$lr_log" \
  && grep -q 'No-Mechanism-Reason' "$lr_log"; then
  record 0 "lesson-ratchet: DCR_TRIGGER_GLOBS fails a prose-only trigger commit (planted RED)"
else
  record 1 "lesson-ratchet: DCR_TRIGGER_GLOBS fails a prose-only trigger commit (planted RED)"
fi
printf 'lesson v2\n' >"$gates_fresh/docs/lesson.md"
printf 'c\n' >"$gates_fresh/checks/c.txt"
git -C "$gates_fresh" add docs/lesson.md checks/c.txt >/dev/null 2>&1
git -C "$gates_fresh" commit -q -m 'feat: lesson with its check'
lr_log="$WORK/lesson-trigger-green.log"
(cd "$gates_fresh" && DCR_TRIGGER_GLOBS='docs/*' DCR_TEST_GLOBS='checks/*' bash "$gates_runner") >"$lr_log" 2>&1 || true
if grep -q 'dcr-gates: fix_class_gate trigger mode PASS' "$lr_log" \
  && grep -q 'dcr-gates: all gates passed' "$lr_log"; then
  record 0 "lesson-ratchet: DCR_TRIGGER_GLOBS passes a trigger commit with a mechanism"
else
  record 1 "lesson-ratchet: DCR_TRIGGER_GLOBS passes a trigger commit with a mechanism"
fi
if (cd "$gates_fresh" && DCR_TRIGGER_GLOBS='   ' bash "$gates_runner") >"$WORK/lesson-trigger-blank.log" 2>&1; then
  lr_rc=0
else
  lr_rc=$?
fi
if [ "$lr_rc" -ne 0 ] && grep -q 'DCR_TRIGGER_GLOBS names no glob' "$WORK/lesson-trigger-blank.log"; then
  record 0 "lesson-ratchet: whitespace-only DCR_TRIGGER_GLOBS fails closed"
else
  record 1 "lesson-ratchet: whitespace-only DCR_TRIGGER_GLOBS fails closed"
fi

# lesson_replay.py: ci.yml wires it (advisory), a vacuous eval is reported
# VACUOUS (exit 0 advisory, exit 1 with --gate), and an eval naming the new
# prose term REPLAYS and passes --gate.
if grep -qF 'python3 scripts/lesson_replay.py --base "$BASE_SHA" --head "$HEAD_SHA"' "$ROOT/.github/workflows/ci.yml"; then
  record 0 "lesson-replay: ci.yml runs lesson_replay.py on the push/PR range"
else
  record 1 "lesson-replay: ci.yml runs lesson_replay.py on the push/PR range"
fi
lrr="$WORK/lesson-replay"
mkdir -p "$lrr/.claude/skills/s/evals"
git -C "$lrr" init -q
git -C "$lrr" config user.email "jane@example.com"
git -C "$lrr" config user.name "Jane Smith"
git -C "$lrr" config commit.gpgsign false
lrr_commit() {  # <prose line> <eval expectation> <subject>
  printf '%s\n' "$1" >>"$lrr/.claude/skills/s/SKILL.md"
  printf '{"evals": [{"id": "e", "prompt": "p", "expected_output": "%s", "expectations": ["%s"]}]}\n' \
    "$2" "$2" >"$lrr/.claude/skills/s/evals/evals.json"
  git -C "$lrr" add -A >/dev/null 2>&1
  git -C "$lrr" commit -q -m "$3"
}
lrr_commit 'Always check widgets.' 'checks widgets' 'feat: base'
lrr_commit 'Quarantine zorbified inputs.' 'always checks widgets first' 'feat: vacuous lesson'
if python3 "$ROOT/scripts/lesson_replay.py" --repo "$lrr" --base HEAD~1 --head HEAD >"$WORK/lrr-adv.log" 2>&1 \
  && grep -q '^VACUOUS ' "$WORK/lrr-adv.log"; then
  record 0 "lesson-replay: vacuous eval reported VACUOUS, advisory exit 0"
else
  record 1 "lesson-replay: vacuous eval reported VACUOUS, advisory exit 0"
fi
if python3 "$ROOT/scripts/lesson_replay.py" --repo "$lrr" --base HEAD~1 --head HEAD --gate >"$WORK/lrr-red.log" 2>&1; then
  lrr_rc=0
else
  lrr_rc=$?
fi
if [ "$lrr_rc" -eq 1 ] && grep -q '^VACUOUS ' "$WORK/lrr-red.log"; then
  record 0 "lesson-replay: --gate fails a VACUOUS lesson with exit 1 (planted RED)"
else
  record 1 "lesson-replay: --gate fails a VACUOUS lesson with exit 1 (planted RED)"
fi
lrr_commit 'Reject frobnicated payloads.' 'rejects frobnicated payloads' 'feat: tied lesson'
if python3 "$ROOT/scripts/lesson_replay.py" --repo "$lrr" --base HEAD~1 --head HEAD --gate >"$WORK/lrr-green.log" 2>&1 \
  && grep -q "^REPLAYS .*names 'frobnicated'" "$WORK/lrr-green.log"; then
  record 0 "lesson-replay: eval naming the new prose term REPLAYS and passes --gate"
else
  record 1 "lesson-replay: eval naming the new prose term REPLAYS and passes --gate"
fi

# ===========================================================================
# dcr-gates opt-in delivery gates — refix_gate.py, priority_gate.py, and focus_gate.py (own
# lane; APPENDED AT THE END by convention). All are OFF by default; a set
# flag with agentic-delivery missing, a bad flag value, or a missing input
# fails closed; each gate FIRES on a planted violation through the runner.
# ===========================================================================

og="$WORK/optin-gates"
mkdir -p "$og/src"
git -C "$og" init -q
git -C "$og" config user.email "jane@example.com"
git -C "$og" config user.name "Jane Smith"
git -C "$og" config commit.gpgsign false
printf 'x = 1\n' >"$og/src/a.txt"
git -C "$og" add src/a.txt >/dev/null 2>&1
git -C "$og" commit -q -m 'chore: init'
gate "$GATES" install --src "$ROOT" --dest "$og" --mode gates
og_runner="$og/scripts/dcr-gates.sh"

# og_run <log> [VAR=value ...] — run the target's runner under env overrides;
# sets OG_RC to its real exit code.
og_run() {
  local log="$1"
  shift
  if env "$@" bash "$og_runner" >"$log" 2>&1; then OG_RC=0; else OG_RC=$?; fi
}

# 1) A set flag with agentic-delivery NOT installed fails closed.
og_run "$WORK/og-nodelivery.log" DCR_REFIX_GATE=1
if [ "$GATE_RC" -eq 0 ] && [ "$OG_RC" -ne 0 ] \
  && grep -q 'refix_gate.py not found (agentic-delivery not installed?) (FAIL, fail closed)' "$WORK/og-nodelivery.log"; then
  record 0 "dcr-gates opt-in: DCR_REFIX_GATE=1 without agentic-delivery fails closed"
else
  record 1 "dcr-gates opt-in: DCR_REFIX_GATE=1 without agentic-delivery fails closed"
fi

cp -R "$ROOT/.claude/skills/agentic-delivery" "$og/.claude/skills/"
rm -rf "$og/.claude/skills/agentic-delivery/scripts/__pycache__"
printf 'x = 2\n' >"$og/src/a.txt"
git -C "$og" add src/a.txt >/dev/null 2>&1
git -C "$og" commit -q -m 'fix(a): clamp x' -m 'No-Test-Reason: fixture commit'
printf 'x  = 2\n' >"$og/src/a.txt"
git -C "$og" add src/a.txt >/dev/null 2>&1
git -C "$og" commit -q -m 'style(a): reformat'

# 2) Default run (no flags): neither opt-in gate runs.
og_run "$WORK/og-default.log"
if [ "$OG_RC" -eq 0 ] && ! grep -qE 'refix_gate|priority_gate|focus_gate' "$WORK/og-default.log"; then
  record 0 "dcr-gates opt-in: all three gates are off by default"
else
  record 1 "dcr-gates opt-in: all three gates are off by default"
fi

# 3) Planted RED: re-touching a just-fixed file with no test/eval change FIRES.
og_run "$WORK/og-refix.log" DCR_REFIX_GATE=1
if [ "$OG_RC" -ne 0 ] && grep -q 'REFIX src/a.txt prior-fix=' "$WORK/og-refix.log" \
  && grep -q 'dcr-gates: refix_gate FAIL' "$WORK/og-refix.log"; then
  record 0 "dcr-gates opt-in: refix_gate fires on a re-touched fixed file (planted RED)"
else
  record 1 "dcr-gates opt-in: refix_gate fires on a re-touched fixed file (planted RED)"
fi

# 4) The same churn with a Refix-Reason: trailer passes.
printf 'x   = 2\n' >"$og/src/a.txt"
git -C "$og" add src/a.txt >/dev/null 2>&1
git -C "$og" commit -q -m 'style(a): align' -m 'Refix-Reason: whitespace only, no behavior change'
og_run "$WORK/og-refix-ok.log" DCR_REFIX_GATE=1
if [ "$OG_RC" -eq 0 ] && grep -q 'dcr-gates: refix_gate PASS' "$WORK/og-refix-ok.log"; then
  record 0 "dcr-gates opt-in: refix_gate passes with a Refix-Reason trailer"
else
  record 1 "dcr-gates opt-in: refix_gate passes with a Refix-Reason trailer"
fi

# 5) A flag value other than unset/0/1 fails closed.
og_run "$WORK/og-badflag.log" DCR_REFIX_GATE=yes
if [ "$OG_RC" -ne 0 ] && grep -q 'FAIL DCR_REFIX_GATE=yes' "$WORK/og-badflag.log"; then
  record 0 "dcr-gates opt-in: an unrecognized flag value fails closed"
else
  record 1 "dcr-gates opt-in: an unrecognized flag value fails closed"
fi

# 6) DCR_PRIORITY_GATE=1 with no input fails closed.
og_run "$WORK/og-prio-noinput.log" DCR_PRIORITY_GATE=1
if [ "$OG_RC" -ne 0 ] && grep -q 'FAIL priority_gate (DCR_PRIORITY_GATE=1 needs' "$WORK/og-prio-noinput.log"; then
  record 0 "dcr-gates opt-in: priority_gate with no input fails closed"
else
  record 1 "dcr-gates opt-in: priority_gate with no input fails closed"
fi

# 7) Planted RED: a presentation PR while a 48h-old P0 has no citing PR FIRES;
#    the same document with a citing open PR passes.
og_prio_json() {  # <file> <prs-json-array>
  printf '{"now":"2026-01-10T12:00:00Z","pr":{"number":7,"labels":["ui"],"paths":["web/app.css"]},"issues":[{"number":3,"labels":["P0"],"created_at":"2026-01-08T12:00:00Z"}],"prs":%s}\n' "$2" >"$1"
}
og_prio_json "$WORK/og-prio-red.json" '[]'
og_prio_json "$WORK/og-prio-ok.json" '[{"number":9,"body":"Refs #3","state":"open"}]'
og_run "$WORK/og-prio-red.log" DCR_PRIORITY_GATE=1 DCR_PRIORITY_JSON="$WORK/og-prio-red.json"
og_red_rc="$OG_RC"
og_run "$WORK/og-prio-ok.log" DCR_PRIORITY_GATE=1 DCR_PRIORITY_JSON="$WORK/og-prio-ok.json"
if [ "$og_red_rc" -ne 0 ] && grep -q 'BLOCKING #3' "$WORK/og-prio-red.log" \
  && [ "$OG_RC" -eq 0 ] && grep -q 'dcr-gates: priority_gate PASS' "$WORK/og-prio-ok.log"; then
  record 0 "dcr-gates opt-in: priority_gate fires on an inversion, passes once cited (planted RED)"
else
  record 1 "dcr-gates opt-in: priority_gate fires on an inversion, passes once cited (planted RED)"
fi

# 8) DCR_FOCUS_GATE=1: when no priority record ever existed the run passes
#    with a notice; an owner-committed OPEN record FIRES on a change outside
#    its scope; a trivially-true acceptance (`true`) never counts as DONE; the
#    gate passes once the owner's real acceptance command exits 0 (DONE).
og_run "$WORK/og-focus-norecord.log" DCR_FOCUS_GATE=1 DCR_OWNER_EMAIL=jane@example.com
if [ "$OG_RC" -eq 0 ] && grep -q 'no priority record ever existed' "$WORK/og-focus-norecord.log" \
  && grep -q 'dcr-gates: focus_gate PASS' "$WORK/og-focus-norecord.log"; then
  record 0 "dcr-gates opt-in: focus_gate with no priority record ever passes with a notice"
else
  record 1 "dcr-gates opt-in: focus_gate with no priority record ever passes with a notice"
fi
og_focus_record() {  # <acceptance-command> <subject>
  printf 'priority: design-alignment\nscope: src/**\nacceptance: %s\n' "$1" >"$og/.claude/PRIORITY.md"
  git -C "$og" add .claude/PRIORITY.md >/dev/null 2>&1
  git -C "$og" commit -q -m "$2"
}
og_focus_record false 'chore: record owner priority'
mkdir -p "$og/web"
printf 'a { color: red; }\n' >"$og/web/app.css"
git -C "$og" add web/app.css >/dev/null 2>&1
git -C "$og" commit -q -m 'style(web): recolor links'
og_run "$WORK/og-focus-red.log" DCR_FOCUS_GATE=1 DCR_OWNER_EMAIL=jane@example.com
og_red_rc="$OG_RC"
og_run "$WORK/og-focus-agent.log" DCR_FOCUS_GATE=1 DCR_OWNER_EMAIL=owner@example.com
og_agent_rc="$OG_RC"
og_focus_record true 'chore: owner records a trivial acceptance'
og_run "$WORK/og-focus-trivial.log" DCR_FOCUS_GATE=1 DCR_OWNER_EMAIL=jane@example.com
og_trivial_rc="$OG_RC"
og_focus_record 'grep -q 2 src/a.txt' 'chore: owner accepts design alignment'
og_run "$WORK/og-focus-ok.log" DCR_FOCUS_GATE=1 DCR_OWNER_EMAIL=jane@example.com
if [ "$og_red_rc" -ne 0 ] && grep -q 'outside scope: web/app.css' "$WORK/og-focus-red.log" \
  && [ "$og_agent_rc" -ne 0 ] && grep -q 'is not the owner' "$WORK/og-focus-agent.log" \
  && [ "$og_trivial_rc" -ne 0 ] && grep -q 'trivially-true acceptance rejected' "$WORK/og-focus-trivial.log" \
  && [ "$OG_RC" -eq 0 ] && grep -q 'dcr-gates: focus_gate PASS' "$WORK/og-focus-ok.log"; then
  record 0 "dcr-gates opt-in: focus_gate fires outside an OPEN priority, rejects a non-owner record, passes once DONE (planted RED)"
else
  record 1 "dcr-gates opt-in: focus_gate fires outside an OPEN priority, rejects a non-owner record, passes once DONE (planted RED)"
fi

# ===========================================================================
# Language-family load isolation (own lane; APPENDED AT THE END by
# convention). The Phase 0-2 floor carries only the cross-language core of
# language-stack-redflags.md; each language family lives in its own routed
# lang-*.md. Pin, structurally, that a Python repo -- the LIGHT floor parsed
# live from SKILL.md's phase table, plus lang-python.md, plus lang-shell.md
# because its CI runs shell in `run:` steps (the Shell row's trigger) --
# reads no other family: no other lang-*.md is in that load set, and no
# content line of any other family file appears verbatim in it. Planted RED:
# pasting one JavaScript bullet back into the parent must FIRE, and a Shell
# row that no longer names CI `run:` steps must FIRE.
# ===========================================================================

# floor_light_refs <skill_dir> — print the LIGHT Phase 0-2 refs (one per
# line): backticked refs in phase rows 0/1/2's Load cell that carry neither
# the " on FULL" nor the " when " qualifier. An independent re-derivation of
# cmd_mustload's parse (a test oracle, not a call into the gate under test).
floor_light_refs() {
  awk -F'|' '
    $0 == "| Phase | Does | Load |" { on = 1; next }
    on && /^\|---/ { next }
    on && !/^\|/ { on = 0 }
    on {
      ph = $2; sub(/^[[:space:]]+/, "", ph)
      if (ph !~ /^[012] /) next
      cell = $4
      while (match(cell, /`[A-Za-z0-9._-]+\.md`/)) {
        ref = substr(cell, RSTART + 1, RLENGTH - 2)
        rest = substr(cell, RSTART + RLENGTH)
        cell = rest
        if (rest ~ /^ on FULL/ || rest ~ /^ when /) continue
        print ref
      }
    }
  ' "$1/SKILL.md" | sort -u
}

# py_only_leaks <skill_dir> — print every line of a family file other than
# Python and shell (content lines >= 25 chars after its 3-line title/trigger
# header) found verbatim in the Python-with-CI-shell load set, plus any other
# lang-*.md named in the floor. Empty output == isolated.
py_only_leaks() {
  local sd="$1" f
  local set_list="$WORK/py-only-set.txt" pats="$WORK/py-only-pats.txt"
  : >"$set_list"
  : >"$pats"
  while IFS= read -r f; do
    case "$f" in
      lang-*.md) printf 'FLOOR NAMES A LANGUAGE FILE: %s\n' "$f" ;;
    esac
    printf '%s\n' "$sd/references/$f" >>"$set_list"
  done < <(floor_light_refs "$sd")
  printf '%s\n' "$sd/SKILL.md" "$sd/references/lang-python.md" "$sd/references/lang-shell.md" >>"$set_list"
  for f in "$sd"/references/lang-*.md; do
    case "$(basename "$f")" in
      lang-python.md|lang-shell.md) continue ;;
    esac
    awk 'NR > 3 && length($0) >= 25' "$f" >>"$pats"
  done
  [ -s "$pats" ] || { printf 'NO FAMILY PATTERNS (fail closed)\n'; return 0; }
  while IFS= read -r f; do
    grep -Fxf "$pats" "$f" | sed "s|^|LEAK $(basename "$f"): |" || true
  done <"$set_list"
}

# shell_row_covers_ci <skill_dir> — succeed only when the parent's Shell row
# routes CI `run:` shell (plus hooks, Dockerfile RUN, Makefile recipes) to
# lang-shell.md, and lang-shell.md's own trigger line names CI `run:` steps.
shell_row_covers_ci() {
  local row
  row="$(grep -F '`lang-shell.md` |' "$1/references/language-stack-redflags.md" || true)"
  printf '%s' "$row" | grep -qF 'CI (`run:`)' \
    && printf '%s' "$row" | grep -qF 'hooks' \
    && printf '%s' "$row" | grep -qF 'Dockerfile `RUN`' \
    && printf '%s' "$row" | grep -qF 'Makefile' \
    && sed -n 3p "$1/references/lang-shell.md" | grep -qF 'CI `run:` steps'
}

dcr_sd="$ROOT/.claude/skills/deep-code-review"
py_floor="$(floor_light_refs "$dcr_sd" | tr '\n' ' ')"
py_leaks="$(py_only_leaks "$dcr_sd")"
if [ -n "$py_floor" ] && [ -z "$py_leaks" ] \
  && grep -qxF '| Python | `lang-python.md` |' "$dcr_sd/references/language-stack-redflags.md" \
  && grep -qxF '## Python' "$dcr_sd/references/lang-python.md" \
  && shell_row_covers_ci "$dcr_sd" \
  && ! grep -qE '^## (Python|JavaScript|Go|Java|Ruby|PHP|C / C\+\+|Rust|SQL)' "$dcr_sd/references/language-stack-redflags.md"; then
  record 0 "language isolation: a Python repo with CI run: shell (floor: ${py_floor}+ lang-python.md + lang-shell.md) loads no other language family"
else
  printf '%s\n' "$py_leaks" | head -5
  record 1 "language isolation: a Python repo with CI run: shell (floor: ${py_floor}+ lang-python.md + lang-shell.md) loads no other language family"
fi

# Every language file on disk is routed from the parent index AND SKILL.md,
# so "load only the languages present" can reach each one.
lang_unrouted=""
for f in "$dcr_sd"/references/lang-*.md; do
  b="$(basename "$f")"
  grep -qF "\`$b\`" "$dcr_sd/references/language-stack-redflags.md" || lang_unrouted="$lang_unrouted $b(parent)"
  grep -qF "\`$b\`" "$dcr_sd/SKILL.md" || lang_unrouted="$lang_unrouted $b(SKILL.md)"
done
if [ -z "$lang_unrouted" ] && [ "$(ls "$dcr_sd"/references/lang-*.md | wc -l | tr -d ' ')" -ge 2 ]; then
  record 0 "language isolation: every lang-*.md is routed from language-stack-redflags.md and SKILL.md"
else
  record 1 "language isolation: every lang-*.md is routed from language-stack-redflags.md and SKILL.md (unrouted:$lang_unrouted)"
fi

# Planted RED: a copy of the skill whose parent re-absorbs one JavaScript
# bullet must be flagged as a leak into the Python-only load set.
iso_sd="$WORK/lang-iso/deep-code-review"
rm -rf "$WORK/lang-iso"
mkdir -p "$WORK/lang-iso"
cp -R "$dcr_sd" "$iso_sd"
awk 'NR > 3 && length($0) >= 25 { print; exit }' "$iso_sd/references/lang-js-ts.md" \
  >>"$iso_sd/references/language-stack-redflags.md"
if py_only_leaks "$iso_sd" | grep -q '^LEAK language-stack-redflags.md: '; then
  record 0 "language isolation: FIRES when another family's content leaks into the Python-only load set (planted RED)"
else
  record 1 "language isolation: FIRES when another family's content leaks into the Python-only load set (planted RED)"
fi

# Planted RED: a Shell row narrowed back to "shell scripts" no longer routes a
# Python repo's CI `run:` shell to lang-shell.md -- the trigger check must FIRE.
sed 's/^| Shell .*| `lang-shell.md` |$/| Shell \/ Bash scripts | `lang-shell.md` |/' \
  "$dcr_sd/references/language-stack-redflags.md" >"$iso_sd/references/language-stack-redflags.md"
if ! shell_row_covers_ci "$iso_sd" \
  && grep -qxF '| Shell / Bash scripts | `lang-shell.md` |' "$iso_sd/references/language-stack-redflags.md"; then
  record 0 "language isolation: FIRES when the Shell row stops routing CI run: shell to lang-shell.md (planted RED)"
else
  record 1 "language isolation: FIRES when the Shell row stops routing CI run: shell to lang-shell.md (planted RED)"
fi

# ---------------------------------------------------------------------------
# pre-push-verify.sh (templates/deep-code-review) — pre-push hook template
# (#1093): reruns the fast lint+unit tier on the pushed range before
# allowing `git push`, so a rebase/merge-conflict resolution (unverified code
# even when the branch's earlier commits were hook-checked) gets checked
# locally before CI. Own fixture repo (a bare "remote" + a working clone),
# since it needs real refs and a real remote-tracking branch, unlike the
# plain `git add` fixtures above.
# ---------------------------------------------------------------------------

PPV="$ROOT/.claude/skills/deep-code-review/templates/pre-push-verify.sh"

ppvroot="$WORK/ppv-fixture"
mkdir -p "$ppvroot"
git init -q --bare "$ppvroot/remote.git"
git init -q -b main "$ppvroot/local"
git -C "$ppvroot/local" config user.email "test@example.com"
git -C "$ppvroot/local" config user.name "Test"
printf 'a\n' >"$ppvroot/local/f.txt"
git -C "$ppvroot/local" add f.txt >/dev/null 2>&1
git -C "$ppvroot/local" commit -qm init >/dev/null 2>&1
git -C "$ppvroot/local" remote add origin "$ppvroot/remote.git"
git -C "$ppvroot/local" push -q origin HEAD:main >/dev/null 2>&1
git -C "$ppvroot/local" remote set-head origin main >/dev/null 2>&1

ppv_local_sha="$(git -C "$ppvroot/local" rev-parse HEAD)"
ppv_zero="0000000000000000000000000000000000000000"

# ppv_run <log> <ref-line> [env=val ...] — feed one stdin ref-line to the hook
# from inside the fixture clone, under `env`'s var=val prefix args (so a
# failing invocation never trips this harness's own `set -e`; same idiom as
# `og_run` above).
ppv_run() {
  local log="$1" line="$2"
  shift 2
  if printf '%s\n' "$line" | (cd "$ppvroot/local" && env "$@" bash "$PPV" origin) >"$log" 2>&1; then
    PPV_RC=0
  else
    PPV_RC=$?
  fi
}

# Case: bash -n — the template itself parses as valid bash.
if bash -n "$PPV"; then
  record 0 "pre-push-verify: bash -n parses the template"
else
  record 1 "pre-push-verify: bash -n parses the template"
fi

# Case: an existing-branch update with a PASSING DCR_PREPUSH_CMD allows the push.
ppv_run "$WORK/ppv-pass.log" "refs/heads/main $ppv_local_sha refs/heads/main $ppv_local_sha" \
  DCR_PREPUSH_CMD=true
if [ "$PPV_RC" -eq 0 ]; then
  record 0 "pre-push-verify: a passing DCR_PREPUSH_CMD allows the push"
else
  record 1 "pre-push-verify: a passing DCR_PREPUSH_CMD allows the push"
fi

# Case: the SAME push, but a FAILING DCR_PREPUSH_CMD blocks it (planted RED).
ppv_run "$WORK/ppv-fail.log" "refs/heads/main $ppv_local_sha refs/heads/main $ppv_local_sha" \
  DCR_PREPUSH_CMD=false
if [ "$PPV_RC" -ne 0 ] && grep -q 'FAIL -- rejecting push' "$WORK/ppv-fail.log"; then
  record 0 "pre-push-verify: a failing DCR_PREPUSH_CMD blocks the push (planted RED)"
else
  record 1 "pre-push-verify: a failing DCR_PREPUSH_CMD blocks the push (planted RED)"
fi

# Case: DCR_PREPUSH_CMD unset fails closed by default (no env=val args below,
# so neither var is set in the hook's environment).
ppv_run "$WORK/ppv-unset.log" "refs/heads/main $ppv_local_sha refs/heads/main $ppv_local_sha"
if [ "$PPV_RC" -ne 0 ] && grep -q 'DCR_PREPUSH_CMD is not set' "$WORK/ppv-unset.log"; then
  record 0 "pre-push-verify: unset DCR_PREPUSH_CMD fails closed by default"
else
  record 1 "pre-push-verify: unset DCR_PREPUSH_CMD fails closed by default"
fi

# Case: the SAME unset config, but DCR_PREPUSH_ALLOW_UNSET=1 lets it through.
ppv_run "$WORK/ppv-unset-allowed.log" "refs/heads/main $ppv_local_sha refs/heads/main $ppv_local_sha" \
  DCR_PREPUSH_ALLOW_UNSET=1
if [ "$PPV_RC" -eq 0 ] && grep -q 'allowing push through' "$WORK/ppv-unset-allowed.log"; then
  record 0 "pre-push-verify: DCR_PREPUSH_ALLOW_UNSET=1 lets an unset tier through"
else
  record 1 "pre-push-verify: DCR_PREPUSH_ALLOW_UNSET=1 lets an unset tier through"
fi

# Case: a deleted ref (local sha all zeros) is skipped -- never runs DCR_PREPUSH_CMD.
ppv_run "$WORK/ppv-delete.log" "refs/heads/gone $ppv_zero refs/heads/gone $ppv_local_sha" \
  DCR_PREPUSH_CMD=false
if [ "$PPV_RC" -eq 0 ] && grep -q 'is a delete -- skipping' "$WORK/ppv-delete.log"; then
  record 0 "pre-push-verify: a deleted ref is skipped, never runs the tier"
else
  record 1 "pre-push-verify: a deleted ref is skipped, never runs the tier"
fi

# Case: a SHA-256-repo-shaped zero id (64 hex chars, not the hardcoded 40-char
# SHA-1 literal) is still detected as a delete and DCR_PREPUSH_CMD never runs.
ppv_zero64="0000000000000000000000000000000000000000000000000000000000000000"
ppv_run "$WORK/ppv-delete64.log" "refs/heads/gone64 $ppv_zero64 refs/heads/gone64 $ppv_local_sha" \
  DCR_PREPUSH_CMD=false
if [ "$PPV_RC" -eq 0 ] && grep -q 'is a delete -- skipping' "$WORK/ppv-delete64.log"; then
  record 0 "pre-push-verify: a 64-hex (SHA-256-shaped) all-zero local sha is still detected as a delete"
else
  record 1 "pre-push-verify: a 64-hex (SHA-256-shaped) all-zero local sha is still detected as a delete"
fi

# Case: pushed-range honesty -- a pushed local sha that does NOT match the
# checked-out HEAD is refused with a clear message, even though the ref line
# looks well-formed and DCR_PREPUSH_CMD would otherwise pass.
ppv_bogus_sha="abababababababababababababababababababab"
ppv_run "$WORK/ppv-honesty-sha.log" "refs/heads/main $ppv_bogus_sha refs/heads/main $ppv_bogus_sha" \
  DCR_PREPUSH_CMD=true
if [ "$PPV_RC" -ne 0 ] && grep -q 'does not match the commit being pushed' "$WORK/ppv-honesty-sha.log"; then
  record 0 "pre-push-verify: a pushed local sha that mismatches checked-out HEAD is refused"
else
  record 1 "pre-push-verify: a pushed local sha that mismatches checked-out HEAD is refused"
fi

# Case: pushed-range honesty -- a dirty working tree is refused even when the
# pushed local sha matches HEAD, since the checked-out tree no longer matches
# what DCR_PREPUSH_CMD would actually verify. Cleaned up immediately after so
# later cases (which assume a clean fixture) are unaffected.
printf 'dirty\n' >>"$ppvroot/local/f.txt"
ppv_run "$WORK/ppv-honesty-dirty.log" "refs/heads/main $ppv_local_sha refs/heads/main $ppv_local_sha" \
  DCR_PREPUSH_CMD=true
git -C "$ppvroot/local" checkout -q -- f.txt
if [ "$PPV_RC" -ne 0 ] && grep -q 'working tree is dirty' "$WORK/ppv-honesty-dirty.log"; then
  record 0 "pre-push-verify: a dirty working tree is refused"
else
  record 1 "pre-push-verify: a dirty working tree is refused"
fi

# Case: whitespace-only DCR_PREPUSH_CMD is treated the same as unset --
# fails closed by default (not run as an empty-but-passing shell command).
ppv_run "$WORK/ppv-blank.log" "refs/heads/main $ppv_local_sha refs/heads/main $ppv_local_sha" \
  'DCR_PREPUSH_CMD=   '
if [ "$PPV_RC" -ne 0 ] && grep -q 'DCR_PREPUSH_CMD is not set' "$WORK/ppv-blank.log"; then
  record 0 "pre-push-verify: whitespace-only DCR_PREPUSH_CMD fails closed like unset"
else
  record 1 "pre-push-verify: whitespace-only DCR_PREPUSH_CMD fails closed like unset"
fi

# Case: the SAME whitespace-only config, but DCR_PREPUSH_ALLOW_UNSET=1 lets
# it through via the unset path (not by running the blank string as a command).
ppv_run "$WORK/ppv-blank-allowed.log" "refs/heads/main $ppv_local_sha refs/heads/main $ppv_local_sha" \
  'DCR_PREPUSH_CMD=   ' DCR_PREPUSH_ALLOW_UNSET=1
if [ "$PPV_RC" -eq 0 ] && grep -q 'allowing push through' "$WORK/ppv-blank-allowed.log"; then
  record 0 "pre-push-verify: whitespace-only DCR_PREPUSH_CMD + ALLOW_UNSET=1 lets the push through"
else
  record 1 "pre-push-verify: whitespace-only DCR_PREPUSH_CMD + ALLOW_UNSET=1 lets the push through"
fi

# Case: DCR_PREPUSH_CMD must not be able to consume the ref list off the
# hook's own stdin. Two refs are pushed in one invocation; the command reads
# (drains) whatever stdin it is handed. If the hook fails to redirect the
# command's stdin from /dev/null, draining eats the second ref line before
# the `while read` loop can see it, so the second ref's check silently never
# runs. The command decides pass/fail from BASE_SHA (distinct per ref, via
# each ref's own remote sha) rather than from anything on stdin, so this
# proves the *loop*, not the command's own logic, is what's under test.
ppv_second_base="1111111111111111111111111111111111111e"
ppv_stdin_cmd="cat >/dev/null; if [ \"\$BASE_SHA\" = \"${ppv_second_base}\" ]; then exit 1; else exit 0; fi"
ppv_two_refs="refs/heads/main $ppv_local_sha refs/heads/main $ppv_local_sha
refs/heads/second $ppv_local_sha refs/heads/second $ppv_second_base"
ppv_run "$WORK/ppv-stdin.log" "$ppv_two_refs" "DCR_PREPUSH_CMD=$ppv_stdin_cmd"
if [ "$PPV_RC" -ne 0 ] && grep -q 'FAIL -- rejecting push of refs/heads/second' "$WORK/ppv-stdin.log"; then
  record 0 "pre-push-verify: DCR_PREPUSH_CMD can't consume the ref list -- the second ref still runs and its failure blocks"
else
  record 1 "pre-push-verify: DCR_PREPUSH_CMD can't consume the ref list -- the second ref still runs and its failure blocks"
fi

# Case: a brand-new branch (remote sha all zeros) computes BASE_SHA as the
# merge-base against the remote's default branch, not the literal zero sha.
git -C "$ppvroot/local" checkout -qb feature >/dev/null 2>&1
printf 'b\n' >>"$ppvroot/local/f.txt"
git -C "$ppvroot/local" commit -qam feature >/dev/null 2>&1
ppv_feat_sha="$(git -C "$ppvroot/local" rev-parse HEAD)"
ppv_expected_base="$(git -C "$ppvroot/local" merge-base origin/main "$ppv_feat_sha")"
ppv_run "$WORK/ppv-newbranch.log" "refs/heads/feature $ppv_feat_sha refs/heads/feature $ppv_zero" \
  'DCR_PREPUSH_CMD=printf "BASE=$BASE_SHA HEAD=$HEAD_SHA\n"'
if [ "$PPV_RC" -eq 0 ] && grep -q "BASE=$ppv_expected_base HEAD=$ppv_feat_sha" "$WORK/ppv-newbranch.log"; then
  record 0 "pre-push-verify: a new-branch push computes BASE_SHA as the merge-base against the remote default branch"
else
  record 1 "pre-push-verify: a new-branch push computes BASE_SHA as the merge-base against the remote default branch"
fi

# Case: a leftover conflict marker inside the PUSHED RANGE rejects the push
# even though DCR_PREPUSH_CMD itself passes (planted RED -- before #1094's
# change the marker check does not exist, so the hook's exit code is 0 and
# this case fails; after the change it fails closed and this case passes).
git -C "$ppvroot/local" checkout -q main >/dev/null 2>&1
printf 'l1\n<<<<<<< HEAD\nl2\n=======\nl3\n>>>>>>> other\n' >"$ppvroot/local/marker.txt"
git -C "$ppvroot/local" add marker.txt >/dev/null 2>&1
git -C "$ppvroot/local" commit -qm marker >/dev/null 2>&1
ppv_marker_sha="$(git -C "$ppvroot/local" rev-parse HEAD)"
ppv_run "$WORK/ppv-marker.log" "refs/heads/main $ppv_marker_sha refs/heads/main $ppv_local_sha" \
  DCR_PREPUSH_CMD=true
if [ "$PPV_RC" -ne 0 ] && grep -q 'leftover conflict marker' "$WORK/ppv-marker.log"; then
  record 0 "pre-push-verify: a leftover conflict marker in the pushed range rejects the push"
else
  record 1 "pre-push-verify: a leftover conflict marker in the pushed range rejects the push"
fi

# Case: the SAME planted marker, but DCR_PREPUSH_ALLOW_UNSET=1 and no
# DCR_PREPUSH_CMD set -- the marker check runs before the unset-command path
# and still blocks (it must not be treated as "nothing configured, let it
# through").
ppv_run "$WORK/ppv-marker-allowed.log" "refs/heads/main $ppv_marker_sha refs/heads/main $ppv_local_sha" \
  DCR_PREPUSH_ALLOW_UNSET=1
if [ "$PPV_RC" -ne 0 ] && grep -q 'leftover conflict marker' "$WORK/ppv-marker-allowed.log"; then
  record 0 "pre-push-verify: DCR_PREPUSH_ALLOW_UNSET=1 does not let a leftover conflict marker through"
else
  record 1 "pre-push-verify: DCR_PREPUSH_ALLOW_UNSET=1 does not let a leftover conflict marker through"
fi

# Case: the SAME marker, but it sits only in the BASE (already on the far
# side of the pushed range, as if the remote already has it) -- a further,
# marker-free commit on top must not be blocked by it.
printf 'clean\n' >"$ppvroot/local/clean.txt"
git -C "$ppvroot/local" add clean.txt >/dev/null 2>&1
git -C "$ppvroot/local" commit -qm clean >/dev/null 2>&1
ppv_clean_sha="$(git -C "$ppvroot/local" rev-parse HEAD)"
ppv_run "$WORK/ppv-marker-in-base.log" "refs/heads/main $ppv_clean_sha refs/heads/main $ppv_marker_sha" \
  DCR_PREPUSH_CMD=true
if [ "$PPV_RC" -eq 0 ] && ! grep -q 'leftover conflict marker' "$WORK/ppv-marker-in-base.log"; then
  record 0 "pre-push-verify: a marker already in the base (outside the pushed range) does not block"
else
  record 1 "pre-push-verify: a marker already in the base (outside the pushed range) does not block"
fi

# Case: HOLD. A DCR_HOLD file in the git common dir refuses every push and
# prints its reason line, even when DCR_PREPUSH_CMD passes (planted RED --
# before the HOLD check existed this push exited 0). The same file also holds
# a push from a linked worktree (the common dir is shared), and a repo-root
# .dcr-hold holds too. Removing the file lifts the hold.
ppv_hold="$(cd "$ppvroot/local" && git rev-parse --git-common-dir)"
case "$ppv_hold" in /*) ;; *) ppv_hold="$ppvroot/local/$ppv_hold" ;; esac
printf 'release freeze: owner review\nsecond line\n' >"$ppv_hold/DCR_HOLD"
ppv_run "$WORK/ppv-hold.log" "refs/heads/main $ppv_clean_sha refs/heads/main $ppv_clean_sha" \
  DCR_PREPUSH_CMD=true
if [ "$PPV_RC" -ne 0 ] && grep -q 'HOLD' "$WORK/ppv-hold.log" \
  && grep -q 'release freeze: owner review' "$WORK/ppv-hold.log" && ! grep -q 'second line' "$WORK/ppv-hold.log"; then
  record 0 "pre-push-verify: a DCR_HOLD file in the common dir refuses the push and prints its reason line"
else
  record 1 "pre-push-verify: a DCR_HOLD file in the common dir refuses the push and prints its reason line"
fi
git -C "$ppvroot/local" worktree add -q "$ppvroot/wt" HEAD >/dev/null 2>&1
if printf 'refs/heads/x %s refs/heads/x %s\n' "$ppv_clean_sha" "$ppv_clean_sha" \
  | (cd "$ppvroot/wt" && env DCR_PREPUSH_CMD=true bash "$PPV" origin) >"$WORK/ppv-hold-wt.log" 2>&1; then
  record 1 "pre-push-verify: the common-dir DCR_HOLD also refuses a push from a linked worktree"
elif grep -q 'release freeze' "$WORK/ppv-hold-wt.log"; then
  record 0 "pre-push-verify: the common-dir DCR_HOLD also refuses a push from a linked worktree"
else
  record 1 "pre-push-verify: the common-dir DCR_HOLD also refuses a push from a linked worktree"
fi
rm -f "$ppv_hold/DCR_HOLD"
printf 'demo freeze\n' >"$ppvroot/local/.dcr-hold"
ppv_run "$WORK/ppv-hold-root.log" "refs/heads/main $ppv_zero refs/heads/main $ppv_clean_sha" \
  DCR_PREPUSH_CMD=true
rm -f "$ppvroot/local/.dcr-hold"
if [ "$PPV_RC" -ne 0 ] && grep -q 'HOLD.*demo freeze' "$WORK/ppv-hold-root.log"; then
  record 0 "pre-push-verify: a repo-root .dcr-hold refuses even a ref delete"
else
  record 1 "pre-push-verify: a repo-root .dcr-hold refuses even a ref delete"
fi
ppv_run "$WORK/ppv-hold-lifted.log" "refs/heads/main $ppv_clean_sha refs/heads/main $ppv_clean_sha" \
  DCR_PREPUSH_CMD=true
if [ "$PPV_RC" -eq 0 ]; then
  record 0 "pre-push-verify: removing the hold file lifts the hold"
else
  record 1 "pre-push-verify: removing the hold file lifts the hold"
fi

# Case: VERDICT CACHE (#1153). The hold-lifted run just above is the first
# real (non-HOLD-blocked) execution of DCR_PREPUSH_CMD=true against
# $ppv_clean_sha, so it already wrote a stamp. The identical
# (commit, base, command) triple now serves from that stamp instead of
# rerunning.
ppv_run "$WORK/ppv-cache-hit.log" "refs/heads/main $ppv_clean_sha refs/heads/main $ppv_clean_sha" \
  DCR_PREPUSH_CMD=true
if [ "$PPV_RC" -eq 0 ] && grep -q 'cached PASS' "$WORK/ppv-cache-hit.log"; then
  record 0 "pre-push-verify: an unchanged commit with the identical gate is served from the stamp cache"
else
  record 1 "pre-push-verify: an unchanged commit with the identical gate is served from the stamp cache"
fi
# A different DCR_PREPUSH_CMD text is a different gate version -- no stamp
# match, so it actually reruns (planted so a bare commit-only key would
# wrongly hit: the command text is part of the cache key).
ppv_run "$WORK/ppv-cache-miss-cmd.log" "refs/heads/main $ppv_clean_sha refs/heads/main $ppv_clean_sha" \
  DCR_PREPUSH_CMD='true # a different gate'
if [ "$PPV_RC" -eq 0 ] && ! grep -q 'cached PASS' "$WORK/ppv-cache-miss-cmd.log" \
  && grep -q 'running:' "$WORK/ppv-cache-miss-cmd.log"; then
  record 0 "pre-push-verify: a changed DCR_PREPUSH_CMD (different gate version) is not served from the cache"
else
  record 1 "pre-push-verify: a changed DCR_PREPUSH_CMD (different gate version) is not served from the cache"
fi
# DCR_PREPUSH_SKIP_CACHE=1 forces a rerun even though the stamp still matches.
ppv_run "$WORK/ppv-cache-skip.log" "refs/heads/main $ppv_clean_sha refs/heads/main $ppv_clean_sha" \
  DCR_PREPUSH_CMD=true DCR_PREPUSH_SKIP_CACHE=1
if [ "$PPV_RC" -eq 0 ] && ! grep -q 'cached PASS' "$WORK/ppv-cache-skip.log" \
  && grep -q 'running:' "$WORK/ppv-cache-skip.log"; then
  record 0 "pre-push-verify: DCR_PREPUSH_SKIP_CACHE=1 forces a rerun despite a matching stamp"
else
  record 1 "pre-push-verify: DCR_PREPUSH_SKIP_CACHE=1 forces a rerun despite a matching stamp"
fi
# A failing DCR_PREPUSH_CMD must never write a stamp -- rerun the identical
# failing command a second time and it must fail again, not read back a
# cached pass from the first (failed) attempt.
ppv_run "$WORK/ppv-cache-fail-1.log" "refs/heads/main $ppv_clean_sha refs/heads/main $ppv_clean_sha" \
  DCR_PREPUSH_CMD=false
ppv_first_fail_rc="$PPV_RC"
ppv_run "$WORK/ppv-cache-fail-2.log" "refs/heads/main $ppv_clean_sha refs/heads/main $ppv_clean_sha" \
  DCR_PREPUSH_CMD=false
if [ "$ppv_first_fail_rc" -ne 0 ] && [ "$PPV_RC" -ne 0 ] \
  && ! grep -q 'cached PASS' "$WORK/ppv-cache-fail-2.log"; then
  record 0 "pre-push-verify: a failing DCR_PREPUSH_CMD writes no stamp -- the identical command still fails on rerun"
else
  record 1 "pre-push-verify: a failing DCR_PREPUSH_CMD writes no stamp -- the identical command still fails on rerun"
fi
# Same commit, same command, but a DIFFERENT base (remote sha) must never
# share a stamp -- DCR_PREPUSH_CMD's own verdict can depend on BASE_SHA (a
# diff-affected test selection), so the base is part of the cache key.
ppv_run "$WORK/ppv-cache-base-1.log" "refs/heads/main $ppv_clean_sha refs/heads/main $ppv_clean_sha" \
  DCR_PREPUSH_CMD='true # base-key-test'
ppv_run "$WORK/ppv-cache-base-2.log" "refs/heads/main $ppv_clean_sha refs/heads/main $ppv_marker_sha" \
  DCR_PREPUSH_CMD='true # base-key-test'
if [ "$PPV_RC" -eq 0 ] && ! grep -q 'cached PASS' "$WORK/ppv-cache-base-2.log" \
  && grep -q 'running:' "$WORK/ppv-cache-base-2.log"; then
  record 0 "pre-push-verify: the same commit against a different base never reuses the other base's stamp"
else
  record 1 "pre-push-verify: the same commit against a different base never reuses the other base's stamp"
fi
# A new commit (content change) never reuses a stale stamp -- the last use
# of this fixture up to the amend case below, so mutating HEAD here is safe
# for every earlier case above.
printf 'more\n' >>"$ppvroot/local/clean.txt"
git -C "$ppvroot/local" commit -qam "more" >/dev/null 2>&1
ppv_new_tree_sha="$(git -C "$ppvroot/local" rev-parse HEAD)"
ppv_run "$WORK/ppv-cache-miss-tree.log" "refs/heads/main $ppv_new_tree_sha refs/heads/main $ppv_new_tree_sha" \
  DCR_PREPUSH_CMD=true
if [ "$PPV_RC" -eq 0 ] && ! grep -q 'cached PASS' "$WORK/ppv-cache-miss-tree.log" \
  && grep -q 'running:' "$WORK/ppv-cache-miss-tree.log"; then
  record 0 "pre-push-verify: a new commit (changed content) never reuses a stale stamp"
else
  record 1 "pre-push-verify: a new commit (changed content) never reuses a stale stamp"
fi
# An amended commit -- IDENTICAL tree, new commit sha (reworded message only)
# -- must also miss: the stamp is keyed on the commit actually being pushed
# and reviewed, not only its content, so two different commits never share a
# verdict even when their trees are byte-identical. The last use of this
# fixture.
git -C "$ppvroot/local" commit -q --amend -m "more (reworded)" >/dev/null 2>&1
ppv_amend_sha="$(git -C "$ppvroot/local" rev-parse HEAD)"
if [ "$(git -C "$ppvroot/local" rev-parse "${ppv_amend_sha}^{tree}")" \
     = "$(git -C "$ppvroot/local" rev-parse "${ppv_new_tree_sha}^{tree}")" ]; then
  record 0 "pre-push-verify: amend fixture setup -- amended commit keeps the same tree, new sha"
else
  record 1 "pre-push-verify: amend fixture setup -- amended commit's tree unexpectedly changed"
fi
ppv_run "$WORK/ppv-cache-amend.log" "refs/heads/main $ppv_amend_sha refs/heads/main $ppv_amend_sha" \
  DCR_PREPUSH_CMD=true
if [ "$PPV_RC" -eq 0 ] && ! grep -q 'cached PASS' "$WORK/ppv-cache-amend.log" \
  && grep -q 'running:' "$WORK/ppv-cache-amend.log"; then
  record 0 "pre-push-verify: an amended commit (same tree, new sha) never reuses the pre-amend stamp"
else
  record 1 "pre-push-verify: an amended commit (same tree, new sha) never reuses the pre-amend stamp"
fi

# ===========================================================================
# Web must-load isolation (own lane; APPENDED AT THE END by convention). The
# `web` archetype must-loads only the parents frontend-a11y.md and
# product-ux-quality.md; their conditional depth lives in routed sub-files
# (a11y-*.md, web-*.md, ux-*.md), each indexed in its parent with a trigger.
# Pin, structurally, that a web review touching no form and no chart -- the
# LIGHT floor parsed live from SKILL.md's phase table, plus the web row's
# must-load refs parsed live from the load map, plus domain-p.md -- loads none
# of the form / chart sub-files (a11y-forms.md, ux-writes.md, ux-dataviz.md):
# none is in that load set, and no content line of any of them appears
# verbatim in it. Also pin that every sub-file is routed from its parent's
# index AND from SKILL.md, and that the form / chart index rows name their
# trigger. Planted RED: pasting one forms bullet back into the parent must
# FIRE, and dropping the ux-dataviz.md index row must FIRE.
# ===========================================================================

# web_mustload_refs <skill_dir> — print the backticked refs in the load map's
# `| web |` row (an independent re-derivation of cmd_mustload's parse).
web_mustload_refs() {
  awk -F'|' '
    $0 == "| Archetype | Default domains | Must-load refs |" { on = 1; next }
    on && /^\|---/ { next }
    on && !/^\|/ { on = 0 }
    on {
      a = $2; gsub(/^[[:space:]]+|[[:space:]]+$/, "", a)
      if (a != "web") next
      cell = $4
      while (match(cell, /`[A-Za-z0-9._-]+\.md`/)) {
        print substr(cell, RSTART + 1, RLENGTH - 2)
        cell = substr(cell, RSTART + RLENGTH)
      }
    }
  ' "$1/SKILL.md" | sort -u
}

# web_plain_leaks <skill_dir> — print every content line (>= 25 chars, after
# the 4-line title / blank / trigger / blank header) of a form or chart
# sub-file found verbatim in the non-form, non-chart web load set, plus any
# form / chart sub-file the load set names outright. Empty output == isolated.
web_plain_leaks() {
  local sd="$1" f
  local set_list="$WORK/web-plain-set.txt" pats="$WORK/web-plain-pats.txt"
  : >"$set_list"
  : >"$pats"
  while IFS= read -r f; do
    case "$f" in
      a11y-forms.md|ux-writes.md|ux-dataviz.md) printf 'LOAD SET NAMES A FORM/CHART FILE: %s\n' "$f" ;;
    esac
    printf '%s\n' "$sd/references/$f" >>"$set_list"
  done < <({ floor_light_refs "$sd"; web_mustload_refs "$sd"; } | sort -u)
  printf '%s\n' "$sd/SKILL.md" "$sd/references/domain-p.md" >>"$set_list"
  for f in a11y-forms.md ux-writes.md ux-dataviz.md; do
    [ -f "$sd/references/$f" ] || { printf 'MISSING SUB-FILE: %s (fail closed)\n' "$f"; continue; }
    awk 'NR > 4 && length($0) >= 25' "$sd/references/$f" >>"$pats"
  done
  [ -s "$pats" ] || { printf 'NO FORM/CHART PATTERNS (fail closed)\n'; return 0; }
  while IFS= read -r f; do
    grep -Fxf "$pats" "$f" | sed "s|^|LEAK $(basename "$f"): |" || true
  done <"$set_list"
}

# web_index_unrouted <skill_dir> — print every a11y-*/web-*/ux-* sub-file not
# named (backticked) in its parent's index or in SKILL.md, and a form / chart
# index row that does not name its trigger. Empty output == fully routed.
web_index_unrouted() {
  local sd="$1" f b parent
  for f in "$sd"/references/a11y-*.md "$sd"/references/web-*.md "$sd"/references/ux-*.md; do
    [ -e "$f" ] || continue
    b="$(basename "$f")"
    case "$b" in
      ux-*) parent="product-ux-quality.md" ;;
      *) parent="frontend-a11y.md" ;;
    esac
    grep -qF "\`$b\`" "$sd/references/$parent" || printf 'UNROUTED %s (parent %s)\n' "$b" "$parent"
    grep -qF "\`$b\`" "$sd/SKILL.md" || printf 'UNROUTED %s (SKILL.md)\n' "$b"
  done
  grep -E '^\| `a11y-forms\.md` \|' "$sd/references/frontend-a11y.md" | grep -qi 'form' \
    || printf 'TRIGGERLESS a11y-forms.md index row\n'
  grep -E '^\| `ux-writes\.md` \|' "$sd/references/product-ux-quality.md" | grep -qi 'form' \
    || printf 'TRIGGERLESS ux-writes.md index row\n'
  grep -E '^\| `ux-dataviz\.md` \|' "$sd/references/product-ux-quality.md" | grep -qi 'chart' \
    || printf 'TRIGGERLESS ux-dataviz.md index row\n'
}

web_set="$({ floor_light_refs "$dcr_sd"; web_mustload_refs "$dcr_sd"; } | sort -u | tr '\n' ' ')"
web_leaks="$(web_plain_leaks "$dcr_sd")"
web_unrouted="$(web_index_unrouted "$dcr_sd")"
web_subs="$(ls "$dcr_sd"/references/a11y-*.md "$dcr_sd"/references/web-*.md "$dcr_sd"/references/ux-*.md 2>/dev/null | wc -l | tr -d ' ')"
if [ -n "$web_set" ] && [ -z "$web_leaks" ] \
  && printf '%s' "$web_set" | grep -qF 'frontend-a11y.md' \
  && printf '%s' "$web_set" | grep -qF 'product-ux-quality.md'; then
  record 0 "web isolation: a non-form, non-chart web review (${web_set}+ domain-p.md) loads none of a11y-forms.md / ux-writes.md / ux-dataviz.md"
else
  printf '%s\n' "$web_leaks" | head -5
  record 1 "web isolation: a non-form, non-chart web review (${web_set}+ domain-p.md) loads none of a11y-forms.md / ux-writes.md / ux-dataviz.md"
fi

if [ -z "$web_unrouted" ] && [ "$web_subs" -ge 14 ]; then
  record 0 "web isolation: every a11y-*/web-*/ux-* sub-file ($web_subs) is routed from its parent's index and SKILL.md; form/chart rows name their trigger"
else
  printf '%s\n' "$web_unrouted" | head -5
  record 1 "web isolation: every a11y-*/web-*/ux-* sub-file ($web_subs) is routed from its parent's index and SKILL.md; form/chart rows name their trigger"
fi

# a11y-focus.md's own trigger and frontend-a11y.md's index row for it must
# both name an off-canvas/collapsed/visually-hidden focusable region (fix11/
# web): such a region still holds focusable content and must not silently
# drop out of either route.
if grep -qi 'off-canvas, collapsed, or visually hidden' "$dcr_sd/references/a11y-focus.md" \
  && grep -E '^\| `a11y-focus\.md` \|' "$dcr_sd/references/frontend-a11y.md" \
     | grep -qi 'off-canvas, collapsed, or visually hidden'; then
  record 0 "web isolation: a11y-focus.md trigger and its frontend-a11y.md index row both name an off-canvas/collapsed/visually-hidden focusable region"
else
  record 1 "web isolation: a11y-focus.md trigger and its frontend-a11y.md index row both name an off-canvas/collapsed/visually-hidden focusable region"
fi

# Planted RED: a copy of the skill whose a11y parent re-absorbs one forms
# bullet must be flagged as a leak into the non-form web load set.
wiso_sd="$WORK/web-iso/deep-code-review"
rm -rf "$WORK/web-iso"
mkdir -p "$WORK/web-iso"
cp -R "$dcr_sd" "$wiso_sd"
awk 'NR > 4 && length($0) >= 25 { print; exit }' "$wiso_sd/references/a11y-forms.md" \
  >>"$wiso_sd/references/frontend-a11y.md"
wiso_leaks="$(web_plain_leaks "$wiso_sd")"
if printf '%s\n' "$wiso_leaks" | grep -q '^LEAK frontend-a11y.md: '; then
  record 0 "web isolation: FIRES when forms depth leaks back into the web must-load set (planted RED)"
else
  record 1 "web isolation: FIRES when forms depth leaks back into the web must-load set (planted RED)"
fi

# Planted RED: a parent index that drops the ux-dataviz.md row leaves the chart
# sub-file unrouted from its parent -- the routing check must FIRE.
cp "$dcr_sd/references/frontend-a11y.md" "$wiso_sd/references/frontend-a11y.md"
grep -vF '| `ux-dataviz.md` |' "$dcr_sd/references/product-ux-quality.md" \
  >"$wiso_sd/references/product-ux-quality.md" || true
# Capture first: piping straight into `grep -q` can SIGPIPE the producer under
# `set -o pipefail` and read as a non-match.
wiso_unrouted="$(web_index_unrouted "$wiso_sd")"
if printf '%s\n' "$wiso_unrouted" | grep -qF 'UNROUTED ux-dataviz.md (parent product-ux-quality.md)' \
  && printf '%s\n' "$wiso_unrouted" | grep -qF 'TRIGGERLESS ux-dataviz.md index row'; then
  record 0 "web isolation: FIRES when a parent index drops a sub-file's row (planted RED)"
else
  record 1 "web isolation: FIRES when a parent index drops a sub-file's row (planted RED)"
fi

# ===========================================================================
# dcr-gates opt-in reaper_lint (own lane; APPENDED AT THE END by convention),
# on the optin-gates target above. Relative DCR_REAPER_LINT_PATHS entries
# resolve against the target's repo root even when the runner is started from
# another directory, and a whitespace-only value fails closed with a named
# message instead of aborting on an empty-array expansion.
# ===========================================================================

mkdir -p "$og/ops"
printf 'pkill -f chromium\n' >"$og/ops/reap.sh"
rl_run() {  # <log> [VAR=value ...] — run the runner from $WORK; sets RL_RC
  local log="$1"
  shift
  if (cd "$WORK" && env DCR_REAPER_LINT=1 "$@" bash "$og_runner") >"$log" 2>&1; then RL_RC=0; else RL_RC=$?; fi
}
rl_run "$WORK/rl-red.log" DCR_REAPER_LINT_PATHS=ops
if [ "$RL_RC" -ne 0 ] && grep -q '\[BROAD_PKILL\]' "$WORK/rl-red.log" \
  && grep -q 'dcr-gates: reaper_lint FAIL' "$WORK/rl-red.log"; then
  record 0 "dcr-gates opt-in: reaper_lint resolves a relative path against the repo root and FIRES (planted RED)"
else
  record 1 "dcr-gates opt-in: reaper_lint resolves a relative path against the repo root and FIRES (planted RED)"
fi
rl_run "$WORK/rl-green.log" DCR_REAPER_LINT_PATHS=src
if [ "$RL_RC" -eq 0 ] && grep -q 'dcr-gates: reaper_lint PASS' "$WORK/rl-green.log"; then
  record 0 "dcr-gates opt-in: reaper_lint passes a clean relative path"
else
  record 1 "dcr-gates opt-in: reaper_lint passes a clean relative path"
fi
rl_run "$WORK/rl-blank.log" DCR_REAPER_LINT_PATHS='   '
if [ "$RL_RC" -ne 0 ] && grep -q 'FAIL reaper_lint (DCR_REAPER_LINT_PATHS names no path)' "$WORK/rl-blank.log"; then
  record 0 "dcr-gates opt-in: whitespace-only DCR_REAPER_LINT_PATHS fails closed"
else
  record 1 "dcr-gates opt-in: whitespace-only DCR_REAPER_LINT_PATHS fails closed"
fi
rm -rf "$og/ops"

# ===========================================================================
# AppSec must-load isolation (own lane; APPENDED AT THE END by convention).
# security-appsec.md is must-load for web, mobile, api / service, and
# agent / LLM / MCP; its conditional depth lives in routed appsec-*.md
# sub-files, each indexed in the parent with a trigger. Pin, structurally,
# that an API review with no file handling and no runtime-compiled template --
# the LIGHT floor parsed live from SKILL.md's phase table, plus the
# `api / service` row's must-load refs parsed live from the load map, plus
# domain-b.md and domain-i.md -- loads neither appsec-files.md nor
# appsec-ssti.md: neither is in that load set, and no content line of either
# appears verbatim in it. Also pin that every appsec-*.md is routed from the
# parent's index AND from SKILL.md, and that the files / template index rows
# name their trigger. Planted RED: pasting one files line back into the
# parent must FIRE, and dropping the appsec-ssti.md index row must FIRE.
# ===========================================================================

# archetype_mustload_refs <skill_dir> <archetype> — print the backticked refs
# in the load map's row for <archetype> (an independent re-derivation of
# cmd_mustload's parse).
archetype_mustload_refs() {
  awk -F'|' -v want="$2" '
    $0 == "| Archetype | Default domains | Must-load refs |" { on = 1; next }
    on && /^\|---/ { next }
    on && !/^\|/ { on = 0 }
    on {
      a = $2; gsub(/^[[:space:]]+|[[:space:]]+$/, "", a)
      if (a != want) next
      cell = $4
      while (match(cell, /`[A-Za-z0-9._-]+\.md`/)) {
        print substr(cell, RSTART + 1, RLENGTH - 2)
        cell = substr(cell, RSTART + RLENGTH)
      }
    }
  ' "$1/SKILL.md" | sort -u
}

# appsec_plain_leaks <skill_dir> — print every content line (>= 25 chars,
# after the 4-line title / blank / trigger / blank header) of appsec-files.md
# or appsec-ssti.md found verbatim in the no-files, no-template API load set,
# plus either sub-file if the load set names it outright. Empty == isolated.
appsec_plain_leaks() {
  local sd="$1" f
  local set_list="$WORK/appsec-plain-set.txt" pats="$WORK/appsec-plain-pats.txt"
  : >"$set_list"
  : >"$pats"
  while IFS= read -r f; do
    case "$f" in
      appsec-files.md|appsec-ssti.md) printf 'LOAD SET NAMES A FILES/TEMPLATE FILE: %s\n' "$f" ;;
    esac
    printf '%s\n' "$sd/references/$f" >>"$set_list"
  done < <({ floor_light_refs "$sd"; archetype_mustload_refs "$sd" "api / service"; } | sort -u)
  printf '%s\n' "$sd/SKILL.md" "$sd/references/domain-b.md" "$sd/references/domain-i.md" >>"$set_list"
  for f in appsec-files.md appsec-ssti.md; do
    [ -f "$sd/references/$f" ] || { printf 'MISSING SUB-FILE: %s (fail closed)\n' "$f"; continue; }
    awk 'NR > 4 && length($0) >= 25' "$sd/references/$f" >>"$pats"
  done
  [ -s "$pats" ] || { printf 'NO FILES/TEMPLATE PATTERNS (fail closed)\n'; return 0; }
  while IFS= read -r f; do
    grep -Fxf "$pats" "$f" | sed "s|^|LEAK $(basename "$f"): |" || true
  done <"$set_list"
}

# appsec_index_unrouted <skill_dir> — print every appsec-*.md not named in a
# `| \`<file>\` |` row of security-appsec.md's index or (backticked) in
# SKILL.md, and a files / template index row that does not name its trigger.
# Empty output == fully routed.
appsec_index_unrouted() {
  local sd="$1" f b
  for f in "$sd"/references/appsec-*.md; do
    [ -e "$f" ] || continue
    b="$(basename "$f")"
    grep -qF "| \`$b\` |" "$sd/references/security-appsec.md" || printf 'UNROUTED %s (parent security-appsec.md)\n' "$b"
    grep -qF "\`$b\`" "$sd/SKILL.md" || printf 'UNROUTED %s (SKILL.md)\n' "$b"
  done
  grep -E '^\| `appsec-files\.md` \|' "$sd/references/security-appsec.md" | grep -qi 'upload' \
    || printf 'TRIGGERLESS appsec-files.md index row\n'
  grep -E '^\| `appsec-ssti\.md` \|' "$sd/references/security-appsec.md" | grep -qi 'template' \
    || printf 'TRIGGERLESS appsec-ssti.md index row\n'
}

api_set="$({ floor_light_refs "$dcr_sd"; archetype_mustload_refs "$dcr_sd" "api / service"; } | sort -u | tr '\n' ' ')"
appsec_leaks="$(appsec_plain_leaks "$dcr_sd")"
appsec_unrouted="$(appsec_index_unrouted "$dcr_sd")"
appsec_subs="$(ls "$dcr_sd"/references/appsec-*.md 2>/dev/null | wc -l | tr -d ' ')"
if [ -n "$api_set" ] && [ -z "$appsec_leaks" ] \
  && printf '%s' "$api_set" | grep -qF 'security-appsec.md' \
  && printf '%s' "$api_set" | grep -qF 'security-api.md'; then
  record 0 "appsec isolation: a no-files, no-template API review (${api_set}+ domain-b.md, domain-i.md) loads neither appsec-files.md nor appsec-ssti.md"
else
  printf '%s\n' "$appsec_leaks" | head -5
  record 1 "appsec isolation: a no-files, no-template API review (${api_set}+ domain-b.md, domain-i.md) loads neither appsec-files.md nor appsec-ssti.md"
fi

if [ -z "$appsec_unrouted" ] && [ "$appsec_subs" -ge 11 ]; then
  record 0 "appsec isolation: every appsec-*.md sub-file ($appsec_subs) is routed from security-appsec.md's index and SKILL.md; files/template rows name their trigger"
else
  printf '%s\n' "$appsec_unrouted" | head -5
  record 1 "appsec isolation: every appsec-*.md sub-file ($appsec_subs) is routed from security-appsec.md's index and SKILL.md; files/template rows name their trigger"
fi

# Planted RED: a copy of the skill whose appsec parent re-absorbs one files
# line must be flagged as a leak into the no-files API load set.
aiso_sd="$WORK/appsec-iso/deep-code-review"
rm -rf "$WORK/appsec-iso"
mkdir -p "$WORK/appsec-iso"
cp -R "$dcr_sd" "$aiso_sd"
awk 'NR > 6 && length($0) >= 25 { print; exit }' "$aiso_sd/references/appsec-files.md" \
  >>"$aiso_sd/references/security-appsec.md"
aiso_leaks="$(appsec_plain_leaks "$aiso_sd")"
if printf '%s\n' "$aiso_leaks" | grep -q '^LEAK security-appsec.md: '; then
  record 0 "appsec isolation: FIRES when files depth leaks back into the API must-load set (planted RED)"
else
  record 1 "appsec isolation: FIRES when files depth leaks back into the API must-load set (planted RED)"
fi

# Planted RED: a parent index that drops the appsec-ssti.md row leaves the
# template sub-file unrouted from its parent -- the routing check must FIRE.
grep -vF '| `appsec-ssti.md` |' "$dcr_sd/references/security-appsec.md" \
  >"$aiso_sd/references/security-appsec.md" || true
# Capture first: piping straight into `grep -q` can SIGPIPE the producer under
# `set -o pipefail` and read as a non-match.
aiso_unrouted="$(appsec_index_unrouted "$aiso_sd")"
if printf '%s\n' "$aiso_unrouted" | grep -qF 'UNROUTED appsec-ssti.md (parent security-appsec.md)' \
  && printf '%s\n' "$aiso_unrouted" | grep -qF 'TRIGGERLESS appsec-ssti.md index row'; then
  record 0 "appsec isolation: FIRES when the parent index drops a sub-file's row (planted RED)"
else
  record 1 "appsec isolation: FIRES when the parent index drops a sub-file's row (planted RED)"
fi

# ---------------------------------------------------------------------------

# ===========================================================================
# AppSec supply/traversal pointer pins (own lane; APPENDED AT THE END by
# convention). A FULL review of an app that ships a dependency manifest,
# lockfile, or CI workflow -- even absent a diff touching any of them -- must
# still load appsec-supply.md (A03): pin that the trigger row names that
# presence-based condition, and structurally pin it against a fixture app
# that carries only a `.github/workflows/` directory (no manifest, no
# lockfile). Also pin that the A05 grep block names a path-traversal (CWE-22)
# sink line pointing at appsec-files.md, so a traversal sink is not left as
# an A05 finding with no routed depth.
# ===========================================================================

supply_trigger_row="$(grep -E '^\| `appsec-supply\.md` \|' "$dcr_sd/references/security-appsec.md")"
if printf '%s' "$supply_trigger_row" | grep -qi 'dependency manifest, lockfile, or CI workflow'; then
  record 0 "appsec pointer: appsec-supply.md's trigger row fires on target-has-manifest/lockfile/CI-workflow, not diff-touch alone"
else
  record 1 "appsec pointer: appsec-supply.md's trigger row fires on target-has-manifest/lockfile/CI-workflow, not diff-touch alone"
fi

# Fixture: an app with only a CI workflow (no lockfile, no dependency
# manifest) -- structurally confirm the trigger's file-presence language
# covers a CI-workflow-only target so a FULL review still loads
# appsec-supply.md.
supply_fixture="$WORK/appsec-supply-fixture"
rm -rf "$supply_fixture"
mkdir -p "$supply_fixture/.github/workflows"
printf 'name: ci\n' >"$supply_fixture/.github/workflows/ci.yml"
if [ -f "$supply_fixture/.github/workflows/ci.yml" ] \
  && printf '%s' "$supply_trigger_row" | grep -qi 'CI workflow'; then
  record 0 "appsec pointer: a CI-workflow-only app fixture matches the appsec-supply.md trigger's CI-workflow clause"
else
  record 1 "appsec pointer: a CI-workflow-only app fixture matches the appsec-supply.md trigger's CI-workflow clause"
fi

traversal_block="$(sed -n '/^## A05:2025/,/^## A06:2025/p' "$dcr_sd/references/security-appsec.md")"
if printf '%s' "$traversal_block" | grep -qi 'path traversal' \
  && printf '%s' "$traversal_block" | grep -qF 'appsec-files.md' \
  && printf '%s' "$traversal_block" | grep -qi 'CWE-22'; then
  record 0 "appsec pointer: A05 grep block names a path-traversal (CWE-22) sink line pointing to appsec-files.md"
else
  record 1 "appsec pointer: A05 grep block names a path-traversal (CWE-22) sink line pointing to appsec-files.md"
fi

# dcr-gates opt-in source_scan_tests (own lane; APPENDED AT THE END by
# convention), on the optin-gates target above. Relative
# DCR_SOURCE_SCAN_LINT_PATHS entries resolve against the target's repo root
# even when the runner is started from another directory, and a
# whitespace-only value fails closed with a named message instead of
# aborting on an empty-array expansion.
# ===========================================================================

mkdir -p "$og/uitests"
cat >"$og/uitests/Disclosure.test.tsx" <<'FIXTURE'
import fs from 'fs';
test('collapses on click', () => {
  const src = fs.readFileSync('./Disclosure.tsx', 'utf8');
  expect(src.includes('aria-expanded')).toBe(true);
});
FIXTURE
ssl_run() {  # <log> [VAR=value ...] — run the runner from $WORK; sets SSL_RC
  local log="$1"
  shift
  if (cd "$WORK" && env DCR_SOURCE_SCAN_LINT=1 "$@" bash "$og_runner") >"$log" 2>&1; then SSL_RC=0; else SSL_RC=$?; fi
}
ssl_run "$WORK/ssl-red.log" DCR_SOURCE_SCAN_LINT_PATHS=uitests
if [ "$SSL_RC" -ne 0 ] && grep -q 'Disclosure.test.tsx:3:' "$WORK/ssl-red.log" \
  && grep -q 'dcr-gates: source_scan_tests FAIL' "$WORK/ssl-red.log"; then
  record 0 "dcr-gates opt-in: source_scan_tests resolves a relative path against the repo root and FIRES (planted RED)"
else
  record 1 "dcr-gates opt-in: source_scan_tests resolves a relative path against the repo root and FIRES (planted RED)"
fi
ssl_run "$WORK/ssl-green.log" DCR_SOURCE_SCAN_LINT_PATHS=src
if [ "$SSL_RC" -eq 0 ] && grep -q 'dcr-gates: source_scan_tests PASS' "$WORK/ssl-green.log"; then
  record 0 "dcr-gates opt-in: source_scan_tests passes a clean relative path"
else
  record 1 "dcr-gates opt-in: source_scan_tests passes a clean relative path"
fi
ssl_run "$WORK/ssl-blank.log" DCR_SOURCE_SCAN_LINT_PATHS='   '
if [ "$SSL_RC" -ne 0 ] && grep -q 'FAIL source_scan_tests (DCR_SOURCE_SCAN_LINT_PATHS names no path)' "$WORK/ssl-blank.log"; then
  record 0 "dcr-gates opt-in: whitespace-only DCR_SOURCE_SCAN_LINT_PATHS fails closed"
else
  record 1 "dcr-gates opt-in: whitespace-only DCR_SOURCE_SCAN_LINT_PATHS fails closed"
fi
rm -rf "$og/uitests"

# ---------------------------------------------------------------------------
# Doctrine pins: prose that must agree with the shipped mechanism it routes to
# (task_ledger.py, surface_check.py) and with agentic-ceo's small-project
# one-agent mode. Whitespace is collapsed so a re-wrap never trips a pin; a
# pinned phrase changing is a deliberate doctrine edit that updates this block.
flat() { tr '\n' ' ' <"$1" | tr -s ' '; }
ceo_flat="$(flat "$ROOT/.claude/skills/agentic-ceo/SKILL.md")"
pin_ok=1
for phrase in 'Split a multi-ask message into one `add --ask` per ask' \
  'TodoWrite may be a per-session view of the ledger, never a second source' \
  'exit 1 = open asks exist, informational' \
  '`next` returns `doing` first, then `.claude/PRIORITY.md`, then the oldest open' \
  'answer `--same T-###` or `--new`'; do
  case "$ceo_flat" in *"$phrase"*) ;; *) printf 'PIN: agentic-ceo SKILL.md lacks: %s\n' "$phrase" >&2; pin_ok=0 ;; esac
done
case "$ceo_flat" in *'near-duplicate ask is refused'*)
  printf 'PIN: agentic-ceo SKILL.md still says a near-duplicate is refused (task_ledger.py asks --same/--new)\n' >&2; pin_ok=0 ;;
esac
if [ "$pin_ok" -eq 1 ]; then
  record 0 "doctrine pin: agentic-ceo ledger doctrine matches task_ledger.py (split asks, TodoWrite view, status exit 1, next order, --same/--new)"
else
  record 1 "doctrine pin: agentic-ceo ledger doctrine matches task_ledger.py (split asks, TodoWrite view, status exit 1, next order, --same/--new)"
fi
case "$(flat "$ROOT/.claude/skills/agentic-delivery/references/roles.md")" in
  *'once a lane is staffed, never self-executes its work'*)
    record 0 "doctrine pin: roles.md Conductor self-execution ban is scoped to a staffed lane (agentic-ceo one-agent mode)" ;;
  *) record 1 "doctrine pin: roles.md Conductor self-execution ban is scoped to a staffed lane (agentic-ceo one-agent mode)" ;;
esac
dev_flat="$(flat "$ROOT/.claude/skills/agentic-delivery/references/dev-env-ownership.md")"
case "$dev_flat" in
  *'it cannot know how a `/version` endpoint derives that id'*'baked in at build time'*)
    record 0 "doctrine pin: dev-env-ownership.md does not over-claim what surface_check can know about a /version id" ;;
  *) record 1 "doctrine pin: dev-env-ownership.md does not over-claim what surface_check can know about a /version id" ;;
esac

# ===========================================================================
# Data must-load isolation (own lane; APPENDED AT THE END by convention).
# data-quality.md is the data / ETL must-load; its conditional depth lives in
# routed data-*.md sub-files, each indexed in the parent with a trigger. Pin,
# structurally, that a plain ETL review with no embeddings / vector index and
# no entity resolution -- the LIGHT floor parsed live from SKILL.md's phase
# table, plus the `data / ETL` row's must-load refs parsed live from the load
# map, plus the default-domain checklists domain-a/d/e/f/g/j.md -- loads
# neither data-ml.md nor data-identity.md: neither is in that load set, and no
# content line of either appears verbatim in it. Also pin that every data-*.md
# sub-file is routed from the parent's index AND from SKILL.md, and that the
# vector-index / identity index rows name their trigger. Planted RED: pasting
# one data-ml.md line back into the parent must FIRE, and dropping the
# data-identity.md index row must FIRE.
# ===========================================================================

# data_plain_leaks <skill_dir> — print every content line (>= 25 chars, after
# the 4-line title / blank / trigger / blank header) of data-ml.md or
# data-identity.md found verbatim in the plain-ETL load set, plus either
# sub-file if the load set names it outright. Empty == isolated.
data_plain_leaks() {
  local sd="$1" f
  local set_list="$WORK/data-plain-set.txt" pats="$WORK/data-plain-pats.txt"
  : >"$set_list"
  : >"$pats"
  while IFS= read -r f; do
    case "$f" in
      data-ml.md|data-identity.md) printf 'LOAD SET NAMES A VECTOR/IDENTITY FILE: %s\n' "$f" ;;
    esac
    printf '%s\n' "$sd/references/$f" >>"$set_list"
  done < <({ floor_light_refs "$sd"; archetype_mustload_refs "$sd" "data / ETL"; } | sort -u)
  printf '%s\n' "$sd/SKILL.md" >>"$set_list"
  for f in domain-a.md domain-d.md domain-e.md domain-f.md domain-g.md domain-j.md; do
    printf '%s\n' "$sd/references/$f" >>"$set_list"
  done
  for f in data-ml.md data-identity.md; do
    [ -f "$sd/references/$f" ] || { printf 'MISSING SUB-FILE: %s (fail closed)\n' "$f"; continue; }
    awk 'NR > 4 && length($0) >= 25' "$sd/references/$f" >>"$pats"
  done
  [ -s "$pats" ] || { printf 'NO VECTOR/IDENTITY PATTERNS (fail closed)\n'; return 0; }
  while IFS= read -r f; do
    [ -f "$f" ] || { printf 'MISSING LOAD-SET FILE: %s (fail closed)\n' "$f"; continue; }
    grep -Fxf "$pats" "$f" | sed "s|^|LEAK $(basename "$f"): |" || true
  done <"$set_list"
}

# data_index_unrouted <skill_dir> — print every data-*.md sub-file not named in
# a `| \`<file>\` |` row of data-quality.md's index or (backticked) in
# SKILL.md, and a vector-index / identity index row that does not name its
# trigger. Empty output == fully routed.
data_index_unrouted() {
  local sd="$1" f b
  for f in "$sd"/references/data-*.md; do
    [ -e "$f" ] || continue
    b="$(basename "$f")"
    [ "$b" = "data-quality.md" ] && continue
    grep -qF "| \`$b\` |" "$sd/references/data-quality.md" || printf 'UNROUTED %s (parent data-quality.md)\n' "$b"
    grep -qF "\`$b\`" "$sd/SKILL.md" || printf 'UNROUTED %s (SKILL.md)\n' "$b"
  done
  grep -E '^\| `data-ml\.md` \|' "$sd/references/data-quality.md" | grep -qi 'vector index' \
    || printf 'TRIGGERLESS data-ml.md index row\n'
  grep -E '^\| `data-identity\.md` \|' "$sd/references/data-quality.md" | grep -qi 'entity identity' \
    || printf 'TRIGGERLESS data-identity.md index row\n'
}

etl_set="$({ floor_light_refs "$dcr_sd"; archetype_mustload_refs "$dcr_sd" "data / ETL"; } | sort -u | tr '\n' ' ')"
data_leaks="$(data_plain_leaks "$dcr_sd")"
data_unrouted="$(data_index_unrouted "$dcr_sd")"
data_subs="$(ls "$dcr_sd"/references/data-*.md 2>/dev/null | grep -v '/data-quality\.md$' | wc -l | tr -d ' ')"
if [ -n "$etl_set" ] && [ -z "$data_leaks" ] \
  && printf '%s' "$etl_set" | grep -qF 'data-quality.md' \
  && printf '%s' "$etl_set" | grep -qF 'performance-db-cost.md'; then
  record 0 "data isolation: a plain ETL review with no vector index and no entity resolution (${etl_set}+ domain-a/d/e/f/g/j.md) loads neither data-ml.md nor data-identity.md"
else
  printf '%s\n' "$data_leaks" | head -5
  record 1 "data isolation: a plain ETL review with no vector index and no entity resolution (${etl_set}+ domain-a/d/e/f/g/j.md) loads neither data-ml.md nor data-identity.md"
fi

if [ -z "$data_unrouted" ] && [ "$data_subs" -ge 8 ]; then
  record 0 "data isolation: every data-*.md sub-file ($data_subs) is routed from data-quality.md's index and SKILL.md; vector-index/identity rows name their trigger"
else
  printf '%s\n' "$data_unrouted" | head -5
  record 1 "data isolation: every data-*.md sub-file ($data_subs) is routed from data-quality.md's index and SKILL.md; vector-index/identity rows name their trigger"
fi

# Planted RED: a copy of the skill whose data parent re-absorbs one vector-
# index line must be flagged as a leak into the plain-ETL load set.
diso_sd="$WORK/data-iso/deep-code-review"
rm -rf "$WORK/data-iso"
mkdir -p "$WORK/data-iso"
cp -R "$dcr_sd" "$diso_sd"
awk 'NR > 6 && length($0) >= 25 { print; exit }' "$diso_sd/references/data-ml.md" \
  >>"$diso_sd/references/data-quality.md"
diso_leaks="$(data_plain_leaks "$diso_sd")"
if printf '%s\n' "$diso_leaks" | grep -q '^LEAK data-quality.md: '; then
  record 0 "data isolation: FIRES when vector-index depth leaks back into the data / ETL must-load set (planted RED)"
else
  record 1 "data isolation: FIRES when vector-index depth leaks back into the data / ETL must-load set (planted RED)"
fi

# Planted RED: a parent index that drops the data-identity.md row leaves the
# identity sub-file unrouted from its parent -- the routing check must FIRE.
grep -vF '| `data-identity.md` |' "$dcr_sd/references/data-quality.md" \
  >"$diso_sd/references/data-quality.md" || true
# Capture first: piping straight into `grep -q` can SIGPIPE the producer under
# `set -o pipefail` and read as a non-match.
diso_unrouted="$(data_index_unrouted "$diso_sd")"
if printf '%s\n' "$diso_unrouted" | grep -qF 'UNROUTED data-identity.md (parent data-quality.md)' \
  && printf '%s\n' "$diso_unrouted" | grep -qF 'TRIGGERLESS data-identity.md index row'; then
  record 0 "data isolation: FIRES when the parent index drops a sub-file's row (planted RED)"
else
  record 1 "data isolation: FIRES when the parent index drops a sub-file's row (planted RED)"
fi

# ===========================================================================
# dcr-gates DCR_CLOSES_LINT through the installed runner (own lane; APPENDED
# AT THE END by convention): an in-set closing keyword PASSES, a planted stray
# keyword naming the same number in ANOTHER repository FAILS (the allowed set
# is keyed on repo + number), DCR_CLOSES_REPO reaches the script as --repo,
# and a set flag with no allowed set fails closed.
# ===========================================================================

clg="$WORK/closes-gate"
mkdir -p "$clg/src"
git -C "$clg" init -q
git -C "$clg" config user.email "jane@example.com"
git -C "$clg" config user.name "Jane Smith"
git -C "$clg" config commit.gpgsign false
printf 'x = 1\n' >"$clg/src/a.txt"
git -C "$clg" add src/a.txt >/dev/null 2>&1
git -C "$clg" commit -q -m 'chore: init'
gate "$GATES" install --src "$ROOT" --dest "$clg" --mode gates
clg_install_rc="$GATE_RC"
rm -rf "$clg/.claude/skills/deep-code-review/scripts/__pycache__"
printf 'x = 2\n' >"$clg/src/a.txt"
git -C "$clg" add src/a.txt >/dev/null 2>&1
git -C "$clg" commit -q -m 'feat(a): widen x' -m 'Closes #12'

# clg_run <log> [VAR=value ...] — run the target's runner with the closes
# lint on; sets CLG_RC to its real exit code.
clg_run() {
  local log="$1"
  shift
  if env DCR_CLOSES_LINT=1 "$@" bash "$clg/scripts/dcr-gates.sh" >"$log" 2>&1; then CLG_RC=0; else CLG_RC=$?; fi
}

clg_run "$WORK/clg-green.log" DCR_CLOSES_ALLOW=12
if [ "$clg_install_rc" -eq 0 ] && [ "$CLG_RC" -eq 0 ] \
  && grep -q 'dcr-gates: closes_lint PASS' "$WORK/clg-green.log"; then
  record 0 "dcr-gates closes_lint: an in-set closing keyword passes (GREEN)"
else
  record 1 "dcr-gates closes_lint: an in-set closing keyword passes (GREEN)"
fi

clg_run "$WORK/clg-noset.log"
if [ "$CLG_RC" -ne 0 ] \
  && grep -q 'FAIL closes_lint (DCR_CLOSES_LINT=1 needs DCR_CLOSES_ALLOW and/or DCR_CLOSES_PR_BODY)' "$WORK/clg-noset.log"; then
  record 0 "dcr-gates closes_lint: a set flag with no allowed set fails closed"
else
  record 1 "dcr-gates closes_lint: a set flag with no allowed set fails closed"
fi

printf 'x = 3\n' >"$clg/src/a.txt"
git -C "$clg" add src/a.txt >/dev/null 2>&1
git -C "$clg" commit -q -m 'chore(a): tidy' -m 'done;closes other/lib#12'
clg_run "$WORK/clg-red.log" DCR_CLOSES_ALLOW=12
clg_red_rc="$CLG_RC"
clg_run "$WORK/clg-repo.log" DCR_CLOSES_ALLOW=12 DCR_CLOSES_REPO=other/lib
if [ "$clg_red_rc" -ne 0 ] && grep -q 'references other/lib#12, not in the allowed set \[#12\]' "$WORK/clg-red.log" \
  && grep -q 'dcr-gates: closes_lint FAIL' "$WORK/clg-red.log" \
  && [ "$CLG_RC" -eq 0 ] && grep -q 'dcr-gates: closes_lint PASS' "$WORK/clg-repo.log"; then
  record 0 "dcr-gates closes_lint: a stray same-number keyword in another repository fails; DCR_CLOSES_REPO reaches --repo (planted RED)"
else
  record 1 "dcr-gates closes_lint: a stray same-number keyword in another repository fails; DCR_CLOSES_REPO reaches --repo (planted RED)"
fi

# ---------------------------------------------------------------------------

# ===========================================================================
# lane-preamble template: shipped, size-bounded, and every script command it
# names actually exists — so a paste-ready command block can't silently rot
# once the script it names moves or is deleted.
# ===========================================================================

lp="$ROOT/.claude/skills/agentic-delivery/templates/lane-preamble.md"
if [ -f "$lp" ]; then
  record 0 "lane-preamble: templates/lane-preamble.md exists"

  lp_lines="$(wc -l <"$lp" | tr -d '[:space:]')"
  if [ "$lp_lines" -le 60 ]; then
    record 0 "lane-preamble: stays within 60 lines ($lp_lines)"
  else
    record 1 "lane-preamble: stays within 60 lines ($lp_lines)"
  fi

  if grep -q 'git diff --check' "$lp" && grep -q 'inventory the old capabilities' "$lp"; then
    record 0 "lane-preamble: names the diff --check and migration-inventory closers"
  else
    record 1 "lane-preamble: names the diff --check and migration-inventory closers"
  fi

  lp_missing=0
  while IFS= read -r lp_script; do
    [ -n "$lp_script" ] || continue
    if [ ! -f "$ROOT/$lp_script" ]; then
      printf 'LANE PREAMBLE SCRIPT MISSING: %s\n' "$lp_script" >&2
      lp_missing=1
    fi
  done < <(grep -oE '\.claude/skills/[A-Za-z0-9_-]+/scripts/[A-Za-z0-9_]+\.py' "$lp" | LC_ALL=C sort -u)
  if [ "$lp_missing" -eq 0 ]; then
    record 0 "lane-preamble: every named script exists under .claude/skills/*/scripts/"
  else
    record 1 "lane-preamble: every named script exists under .claude/skills/*/scripts/"
  fi

  # Every `<script> <subcommand> --flag` paste-ready command in the template
  # must resolve to a real subcommand/flag on that script's own --help output
  # today — so a renamed/removed flag or subcommand rots the doc, not silently.
  lp_flag_report="$WORK/lp-flag-check.txt"
  if python3 - "$lp" "$ROOT" >"$lp_flag_report" 2>&1 <<'PY'
import re
import shlex
import subprocess
import sys
from pathlib import Path

lp_path, root = sys.argv[1], Path(sys.argv[2])
text = Path(lp_path).read_text(encoding="utf-8")
cmds = re.findall(r"`([^`]*\.py[^`]*)`", text)

SCRIPT_RE = re.compile(r"\.claude/skills/[A-Za-z0-9_-]+/scripts/[A-Za-z0-9_]+\.py")
SUBS_RE = re.compile(r"\{([A-Za-z0-9_,-]+)\}\s*\.\.\.")

help_cache: dict[tuple, str] = {}


def help_text(script: Path, sub: str | None) -> str:
    key = (str(script), sub)
    if key in help_cache:
        return help_cache[key]
    argv = ["python3", str(script)] + ([sub] if sub else []) + ["--help"]
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=20)
        combined = out.stdout + out.stderr
    except Exception as exc:  # pragma: no cover - defensive
        combined = f"(--help failed: {exc})"
    help_cache[key] = combined
    return combined


ok = True
for cmd in cmds:
    m = SCRIPT_RE.search(cmd)
    if not m:
        continue
    rel = m.group(0)
    script = root / rel
    if not script.is_file():
        continue  # already reported by the exists-check above
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        print(f"UNPARSEABLE COMMAND: {cmd}")
        ok = False
        continue
    try:
        si = next(i for i, t in enumerate(tokens) if t.endswith(rel))
    except StopIteration:
        continue
    rest = tokens[si + 1 :]
    base_help = help_text(script, None)
    subs_m = SUBS_RE.search(base_help)
    subcommand = None
    flag_start = 0
    if subs_m:
        subs = set(subs_m.group(1).split(","))
        if rest and not rest[0].startswith("--") and not rest[0].startswith("<"):
            subcommand = rest[0]
            flag_start = 1
            if subcommand not in subs:
                print(f"UNKNOWN SUBCOMMAND: {rel} {subcommand} (valid: {sorted(subs)})")
                ok = False
                continue
    help_out = help_text(script, subcommand) if subcommand else base_help
    known_flags = set(re.findall(r"(--[A-Za-z][A-Za-z0-9-]*)", help_out))
    for tok in rest[flag_start:]:
        if tok.startswith("--"):
            flag = tok.split("=", 1)[0]
            if flag not in known_flags:
                print(f"UNKNOWN FLAG: {rel} {subcommand or ''} {flag}")
                ok = False

sys.exit(0 if ok else 1)
PY
  then
    record 0 "lane-preamble: every <script> <subcommand> --flag matches its --help"
  else
    cat "$lp_flag_report" >&2
    record 1 "lane-preamble: every <script> <subcommand> --flag matches its --help"
  fi
else
  record 1 "lane-preamble: templates/lane-preamble.md exists"
fi

# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Cost vs quality guardrails (agentic-delivery/references/
# cost-quality-guardrails.md): a cost cut may move prose behind a trigger, but
# (1) every anchor in scripts/floor-anchors.tsv stays, as a fixed string, in
# its must-load file, and (2) every routed reference keeps a trigger that its
# router line echoes (scripts/trigger_lint.py; free and deterministic, while
# LLM trigger evals run once per release).
# ---------------------------------------------------------------------------
# floor_anchor_misses <manifest>: prints one line per row whose heading or
# body anchor is empty or absent from its file, or that does not have exactly
# four tab-separated columns; prints nothing when all hold. An empty anchor is
# a miss (grep -F "" would match every file). Columns are split by parameter
# expansion, not `IFS=$'\t' read`, because tab is IFS whitespace and read
# would collapse an empty column into its neighbour.
floor_anchor_misses() {
  local line tabs file heading body why rest a
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    tabs="${line//[!$'\t']/}"
    if [ "${#tabs}" -ne 3 ]; then
      printf 'FLOOR ANCHOR ROW MALFORMED (want 4 tab-separated columns): %s\n' "$line"
      continue
    fi
    file="${line%%$'\t'*}"; rest="${line#*$'\t'}"
    heading="${rest%%$'\t'*}"; rest="${rest#*$'\t'}"
    body="${rest%%$'\t'*}"; why="${rest#*$'\t'}"
    for a in "$heading" "$body"; do
      if [ -z "$a" ] || ! grep -qF -- "$a" "$ROOT/$file" 2>/dev/null; then
        printf 'FLOOR ANCHOR MISSING: %s: "%s" (%s)\n' "$file" "$a" "$why"
      fi
    done
  done < "$1"
}
fa_rows="$(grep -cvE '^(#|$)' "$ROOT/scripts/floor-anchors.tsv")"
fa_out="$(floor_anchor_misses "$ROOT/scripts/floor-anchors.tsv")"
if [ "$fa_rows" -gt 0 ] && [ -z "$fa_out" ]; then
  record 0 "floor-anchors: every must-load heading+body anchor is still present ($fa_rows rows)"
else
  printf '%s\n' "$fa_out" >&2
  record 1 "floor-anchors: every must-load heading+body anchor is still present ($fa_rows rows)"
fi

# Planted defects: a body phrase gutted from its rule, and an empty anchor,
# must each be reported (the check can go red).
fa_plant="$WORK/floor-anchors-plant.tsv"
printf '.claude/skills/deep-code-review/SKILL.md\t1. **Evidence over opinion.**\tthis body phrase was cut\tplanted\n' > "$fa_plant"
if [ -n "$(floor_anchor_misses "$fa_plant")" ]; then
  record 0 "floor-anchors: a gutted rule body is detected (planted defect)"
else
  record 1 "floor-anchors: a gutted rule body is detected (planted defect)"
fi
printf '.claude/skills/deep-code-review/SKILL.md\t1. **Evidence over opinion.**\t\tplanted\n' > "$fa_plant"
if [ -n "$(floor_anchor_misses "$fa_plant")" ]; then
  record 0 "floor-anchors: an empty anchor is a failure, not a match-everything pass (planted defect)"
else
  record 1 "floor-anchors: an empty anchor is a failure, not a match-everything pass (planted defect)"
fi
printf '.claude/skills/deep-code-review/SKILL.md\t1. **Evidence over opinion.**\n' > "$fa_plant"
if [ -n "$(floor_anchor_misses "$fa_plant")" ]; then
  record 0 "floor-anchors: a row missing its body column is a failure (planted defect)"
else
  record 1 "floor-anchors: a row missing its body column is a failure (planted defect)"
fi

if tl_out="$(python3 "$ROOT/scripts/trigger_lint.py" "$ROOT" 2>&1)"; then
  record 0 "trigger-lint: every routed reference's trigger is echoed by its router line"
else
  printf '%s\n' "$tl_out" >&2
  record 1 "trigger-lint: every routed reference's trigger is echoed by its router line"
fi

# ===========================================================================
# --apply-operating-layer: jq-merge is idempotent (apply twice -> identical
# file, one hook entry per template entry), writes the lane agent once, and
# update-installed.sh replays the recorded flags.
# ===========================================================================
if command -v jq >/dev/null 2>&1; then
  OPA="$WORK/oplayer-target"
  mkdir -p "$OPA/.claude"
  echo '{"model":"opus"}' >"$OPA/.claude/settings.local.json"
  bash "$ROOT/install.sh" --with-delivery --apply-operating-layer "$OPA" >"$WORK/opa1.log" 2>&1
  cp "$OPA/.claude/settings.local.json" "$WORK/opa.first"
  DCR_NO_PULL=1 bash "$ROOT/scripts/update-installed.sh" "$OPA" >"$WORK/opa2.log" 2>&1
  if cmp -s "$WORK/opa.first" "$OPA/.claude/settings.local.json" \
    && [ "$(jq '.hooks.SubagentStart | length' "$OPA/.claude/settings.local.json")" = 1 ] \
    && [ "$(jq '.hooks.SubagentStop | length' "$OPA/.claude/settings.local.json")" = 1 ] \
    && [ "$(jq -r .model "$OPA/.claude/settings.local.json")" = opus ] \
    && compgen -G "$OPA/.claude/settings.local.json.bak.*" >/dev/null \
    && [ -f "$OPA/.claude/agents/delivery-lane.md" ]; then
    record 0 "operating-layer: apply twice is idempotent, single hook entries"
  else
    record 1 "operating-layer: apply twice is idempotent, single hook entries"
  fi
fi

# ===========================================================================
# update-installed.sh pulls first: a clone behind its origin is fast-forwarded
# (and the new version printed); a dirty clone is refused.
# ===========================================================================
UI="$WORK/ui"
mkdir -p "$UI/seed/scripts" "$UI/seed/.claude/skills/deep-code-review" "$UI/tgt/.claude"
cp "$ROOT/scripts/update-installed.sh" "$UI/seed/scripts/"
printf '#!/usr/bin/env bash\nexit 0\n' >"$UI/seed/install.sh"
echo 1.0.0 >"$UI/seed/.claude/skills/deep-code-review/VERSION"
: >"$UI/tgt/.claude/.dcr-install-flags"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
git -C "$UI/seed" init -q -b main
git -C "$UI/seed" add -A
git -C "$UI/seed" commit -qm v1
git clone -q "$UI/seed" "$UI/clone"
echo 2.0.0 >"$UI/seed/.claude/skills/deep-code-review/VERSION"
git -C "$UI/seed" commit -qam v2
ui_out="$(bash "$UI/clone/scripts/update-installed.sh" "$UI/tgt" 2>&1)" || true
echo 3.0.0 >"$UI/seed/.claude/skills/deep-code-review/VERSION"
git -C "$UI/seed" commit -qam v3
echo dirty >>"$UI/clone/install.sh"
ui_dirty="$(bash "$UI/clone/scripts/update-installed.sh" "$UI/tgt" 2>&1)" && ui_rc=0 || ui_rc=$?
if [ "$(cat "$UI/clone/.claude/skills/deep-code-review/VERSION")" = 2.0.0 ] \
  && printf '%s' "$ui_out" | grep -q "dcr version: 2.0.0" \
  && [ "$ui_rc" -ne 0 ] && printf '%s' "$ui_dirty" | grep -q "uncommitted changes"; then
  record 0 "update-installed: fast-forwards a behind clone, refuses a dirty one"
else
  record 1 "update-installed: fast-forwards a behind clone, refuses a dirty one"
fi

# update-installed.sh infers flags when the install marker is missing (own per-feature file).
if bash "$ROOT/scripts/test-update-installed-infer.sh" >"$WORK/ui-infer.log" 2>&1; then
  record 0 "update-installed: infers flags and writes the marker when missing"
else
  cat "$WORK/ui-infer.log" >&2
  record 1 "update-installed: infers flags and writes the marker when missing"
fi

# test-train-scripts.sh SKIPs (never hangs) when pgrep/ps are unavailable: own per-feature file.
if bash "$ROOT/scripts/test-no-hang-without-pgrep.sh" >"$WORK/nopgrep.log" 2>&1; then
  record 0 "train scripts: reap_own blocks SKIP and return when pgrep/ps are unavailable"
else
  record 1 "train scripts: reap_own blocks SKIP and return when pgrep/ps are unavailable"; tail -5 "$WORK/nopgrep.log"
fi

# merge-train scripts: own per-feature file (scripts/test-train-scripts.sh), one case here.
if bash "$ROOT/scripts/test-train-scripts.sh" >"$WORK/train-scripts.log" 2>&1; then
  record 0 "train scripts: land_train/train_land/reap_own tests pass"
else
  record 1 "train scripts: land_train/train_land/reap_own tests pass"; tail -5 "$WORK/train-scripts.log"
fi

# delivery friction: gh TLS curl fallback, fail-closed gh failures, lock holder reporting; own per-feature file, one case here.
if bash "$ROOT/scripts/test-delivery-friction.sh" >"$WORK/delivery-friction.log" 2>&1; then
  record 0 "delivery friction: gh_rest curl fallback, could-not-check fail-closed, lock holder status"
else
  record 1 "delivery friction: gh_rest curl fallback, could-not-check fail-closed, lock holder status"; tail -8 "$WORK/delivery-friction.log"
fi

# train hardening (#1341): own per-feature file (scripts/test-train-hardening.sh), one case here.
if bash "$ROOT/scripts/test-train-hardening.sh" >"$WORK/train-hardening.log" 2>&1; then
  record 0 "train hardening: spaced UNION_DIRS, per-worktree lock, exit 3 on no GREEN union"
else
  record 1 "train hardening: spaced UNION_DIRS, per-worktree lock, exit 3 on no GREEN union"; tail -8 "$WORK/train-hardening.log"
fi

# train id normalizer: own per-feature file (scripts/test-train-id-normalize.sh), one case here.
if bash "$ROOT/scripts/test-train-id-normalize.sh" >"$WORK/train-idnorm.log" 2>&1; then
  record 0 "train ids: trailing space/CRLF on a FAIL id still matches (one normalizer)"
else
  record 1 "train ids: trailing space/CRLF on a FAIL id still matches (one normalizer)"; tail -8 "$WORK/train-idnorm.log"
fi

# train fail-closed parsers: own per-feature file (scripts/test-train-failclosed.sh), one case here.
if bash "$ROOT/scripts/test-train-failclosed.sh" >"$WORK/train-failclosed.log" 2>&1; then
  record 0 "train fail-closed: missing failed-ids list and GREEN-with-nonzero-rc are not a pass"
else
  record 1 "train fail-closed: missing failed-ids list and GREEN-with-nonzero-rc are not a pass"; tail -8 "$WORK/train-failclosed.log"
fi

# train resilience: own per-feature file (scripts/test-train-resilience.sh), one case here.
if bash "$ROOT/scripts/test-train-resilience.sh" >"$WORK/train-resilience.log" 2>&1; then
  record 0 "train resilience: flake re-run triage, exclusive gate lease, mkdir locks"
else
  record 1 "train resilience: flake re-run triage, exclusive gate lease, mkdir locks"; tail -8 "$WORK/train-resilience.log"
fi

# train base-red guard: own per-feature file (scripts/test-train-red-base.sh), one case here.
if bash "$ROOT/scripts/test-train-red-base.sh" >"$WORK/train-red-base.log" 2>&1; then
  record 0 "train base-red guard: pre-existing browser failures excused, new ones block"
else
  record 1 "train base-red guard: pre-existing browser failures excused, new ones block"; tail -8 "$WORK/train-red-base.log"
fi

# train flake rate: own per-feature file (scripts/test-train-flake-rate.sh), one case here.
if bash "$ROOT/scripts/test-train-flake-rate.sh" >"$WORK/train-flake-rate.log" 2>&1; then
  record 0 "train flake rate: all-N REAL rule, per-tree verdict cache, gate backoff, keystone TMPDIR"
else
  record 1 "train flake rate: all-N REAL rule, per-tree verdict cache, gate backoff, keystone TMPDIR"; tail -8 "$WORK/train-flake-rate.log"
fi

# train flake-on-base: own per-feature file (scripts/test-train-flake-base.sh), one case here.
if bash "$ROOT/scripts/test-train-flake-base.sh" >"$WORK/train-flake-base.log" 2>&1; then
  record 0 "train flake-on-base: a FLAKE lands only if the test also fails on the base, else CANT"
else
  record 1 "train flake-on-base: a FLAKE lands only if the test also fails on the base, else CANT"; tail -8 "$WORK/train-flake-base.log"
fi

# peer pains: own per-feature file (scripts/test-peer-pains-2.sh), one case here.
if bash "$ROOT/scripts/test-peer-pains-2.sh" >"$WORK/peer-pains-2.log" 2>&1; then
  record 0 "peer pains: train CANT rule, no unchecked-as-zero status, NOT CHECKED briefs"
else
  record 1 "peer pains: train CANT rule, no unchecked-as-zero status, NOT CHECKED briefs"; tail -8 "$WORK/peer-pains-2.log"
fi

# fleet lessons: own per-feature file (scripts/test-fleet-lessons.sh), one case here.
if bash "$ROOT/scripts/test-fleet-lessons.sh" >"$WORK/fleet-lessons.log" 2>&1; then
  record 0 "fleet lessons: same-host baselines, fresh-store per-title re-runs, process-group timebox"
else
  record 1 "fleet lessons: same-host baselines, fresh-store per-title re-runs, process-group timebox"; tail -8 "$WORK/fleet-lessons.log"
fi

# land-release: own per-feature file (scripts/test-land-release.sh), one case here.
if bash "$ROOT/scripts/test-land-release.sh" >"$WORK/land-release.log" 2>&1; then
  record 0 "land-release: two fragment lanes land back-to-back with no rebump"
else
  record 1 "land-release: two fragment lanes land back-to-back with no rebump"; tail -8 "$WORK/land-release.log"
fi

# PR-native review workflow template: own per-feature file (scripts/test-pr-review-workflow.sh), one case here.
if bash "$ROOT/scripts/test-pr-review-workflow.sh" >"$WORK/pr-review-wf.log" 2>&1; then
  record 0 "perun-review.yml: least-privilege permissions, pull_request only, opt-in"
else
  record 1 "perun-review.yml: least-privilege permissions, pull_request only, opt-in"; tail -8 "$WORK/pr-review-wf.log"
fi

# Repo-access review default: own per-feature file (scripts/test_agentic_review_default.py), one case here.
if python3 "$ROOT/scripts/test_agentic_review_default.py" >"$WORK/agentic-default.log" 2>&1; then
  record 0 "agentic default: /review, PR workflow and SKILL.md require repo access"
else
  record 1 "agentic default: /review, PR workflow and SKILL.md require repo access"; tail -8 "$WORK/agentic-default.log"
fi

# must-load floor cut: own per-feature file (scripts/test-mustload-split.sh), one case here.
if bash "$ROOT/scripts/test-mustload-split.sh" >"$WORK/mustload-split.log" 2>&1; then
  record 0 "mustload split: moved sections stay present and routed; INDEX has no Headings column"
else
  record 1 "mustload split: moved sections stay present and routed; INDEX has no Headings column"; tail -8 "$WORK/mustload-split.log"
fi

# ultrareview fixes: own per-feature file (scripts/test-ultrareview-fixes.sh), one case here.
if bash "$ROOT/scripts/test-ultrareview-fixes.sh" >"$WORK/ultrareview.log" 2>&1; then
  record 0 "ultrareview fixes: operating-layer placeholder, reap_own, update-installed, inject guards"
else
  record 1 "ultrareview fixes: operating-layer placeholder, reap_own, update-installed, inject guards"; tail -8 "$WORK/ultrareview.log"
fi

# host safety: own per-feature file (scripts/test-host-safety.sh), one case here.
if bash "$ROOT/scripts/test-host-safety.sh" >"$WORK/host-safety.log" 2>&1; then
  record 0 "host safety: install warns per host, selfcheck reports per-host sandbox status"
else
  record 1 "host safety: install warns per host, selfcheck reports per-host sandbox status"; tail -8 "$WORK/host-safety.log"
fi

# destructive guard: own per-feature file (scripts/test-destructive-guard.sh), one case here.
if bash "$ROOT/scripts/test-destructive-guard.sh" >"$WORK/destructive-guard.log" 2>&1; then
  record 0 "destructive guard: bench corpus recall >= 28/32, FP <= 1/30, owner allow line"
else
  record 1 "destructive guard: bench corpus recall >= 28/32, FP <= 1/30, owner allow line"; tail -8 "$WORK/destructive-guard.log"
fi

# sandbox by default: own per-feature file (scripts/test-sandbox-default.sh), one case here.
if bash "$ROOT/scripts/test-sandbox-default.sh" >"$WORK/sandbox-default.log" 2>&1; then
  record 0 "sandbox default: operating layer sets sandbox + deny rules, selfcheck flags off"
else
  record 1 "sandbox default: operating layer sets sandbox + deny rules, selfcheck flags off"; tail -8 "$WORK/sandbox-default.log"
fi

# auto-context-reset: own per-feature file (scripts/test-auto-context-reset.sh), one case here.
if bash "$ROOT/scripts/test-auto-context-reset.sh" >"$WORK/auto-context-reset.log" 2>&1; then
  record 0 "auto-context-reset: autoCompactWindow never clobbers a user value, handoff hook output capped"
else
  record 1 "auto-context-reset: autoCompactWindow never clobbers a user value, handoff hook output capped"; tail -8 "$WORK/auto-context-reset.log"
fi

# host-command-hints: own per-feature file (scripts/test-host-command-hints.sh), one case here.
if bash "$ROOT/scripts/test-host-command-hints.sh" >"$WORK/host-command-hints.log" 2>&1; then
  record 0 "host-command-hints: context_nudge names each host's documented commands and a model/effort tier, two lines at most"
else
  record 1 "host-command-hints: context_nudge names each host's documented commands and a model/effort tier, two lines at most"; tail -8 "$WORK/host-command-hints.log"
fi

# first-run prompt: installer output and AGENTS.md block give a portable plain-words prompt (no remote/slash needed).
FR="$WORK/firstrun"; mkdir -p "$FR"
if bash "$ROOT/install.sh" "$FR" >"$FR.out" 2>&1 && grep -q "run a deep code review FILE" "$FR.out" && grep -q "run a deep code review FILE" "$FR/AGENTS.md" && sed -n '/^3\. \*\*Ask your agent/,/^>/p' "$ROOT/README.md" | head -2 | grep -q 'review FILE'; then
  record 0 "first-run prompt: installer + AGENTS.md show plain-words FILE prompt, README step 3 leads with FILE"
else
  record 1 "first-run prompt: installer + AGENTS.md show plain-words FILE prompt, README step 3 leads with FILE"; tail -5 "$FR.out"
fi

# ops-script edge cases: own per-feature file (scripts/test-ops-edge.sh), one case here.
if bash "$ROOT/scripts/test-ops-edge.sh" >"$WORK/ops-edge.log" 2>&1; then
  record 0 "ops edge cases: clean_finished/land_train/prefile_check/pipe_mask_guard"
else
  record 1 "ops edge cases: clean_finished/land_train/prefile_check/pipe_mask_guard"; tail -5 "$WORK/ops-edge.log"
fi

# secret gate recall/precision: own per-feature file (scripts/test-secret-gate-recall.sh), one case here.
if bash "$ROOT/scripts/test-secret-gate-recall.sh" >"$WORK/secret-recall.log" 2>&1; then
  record 0 "secret gate: banlist catches common token/key/PII shapes, spares placeholders"
else
  record 1 "secret gate: banlist catches common token/key/PII shapes, spares placeholders"; tail -5 "$WORK/secret-recall.log"
fi

# loop templates: own per-feature file (scripts/test-loop-templates.sh), one case here.
if bash "$ROOT/scripts/test-loop-templates.sh" >"$WORK/loop-templates.log" 2>&1; then
  record 0 "loop templates: scripts exist, >=20 min, installed, routed"
else
  record 1 "loop templates: scripts exist, >=20 min, installed, routed"; tail -5 "$WORK/loop-templates.log"
fi

# tracker hygiene (own per-feature file scripts/test_tracker_hygiene.py): stubbed gh, fake GraphQL server, install block.
if python3 "$ROOT/scripts/test_tracker_hygiene.py" >"$WORK/tracker-hygiene.log" 2>&1; then
  record 0 "tracker hygiene: tracker_check/weekly_update/install --tracker-project"
else
  record 1 "tracker hygiene: tracker_check/weekly_update/install --tracker-project"; tail -8 "$WORK/tracker-hygiene.log"
fi

# impact_map.py / context_pack.py: own per-feature file (scripts/test_impact_map.py), one case here.
if python3 "$ROOT/scripts/test_impact_map.py" >"$WORK/impact-map.log" 2>&1; then
  record 0 "impact_map/context_pack: callers, callees, caps, bounded pack on a synthetic repo"
else
  record 1 "impact_map/context_pack: callers, callees, caps, bounded pack on a synthetic repo"; tail -5 "$WORK/impact-map.log"
fi

# install.sh AGENTS.md blocks are compact (<= 6 lines each, markers included)
# and a re-run replaces them in place (idempotent), so a target repo's own
# AGENTS.md size gate is not broken by the default install (#1309).
dest_ag="$WORK/dest-agents-compact"
mkdir -p "$dest_ag"
bash "$ROOT/install.sh" --full --with-delivery --with-critic --with-comms --with-contribution --with-discovery --with-ceo --with-growth --with-positioning --with-business --with-output-safety "$dest_ag" >/dev/null 2>&1
bash "$ROOT/install.sh" --full --with-delivery --with-critic --with-comms --with-contribution --with-discovery --with-ceo --with-growth --with-positioning --with-business --with-output-safety "$dest_ag" >/dev/null 2>&1
ag_ok=1
for m in deep-code-review dcr-overlays; do
  n="$(awk -v b="<!-- $m:begin -->" -v e="<!-- $m:end -->" '$0==b{s=1} s{c++} $0==e{s=0} END{print c+0}' "$dest_ag/AGENTS.md")"
  [ "$n" -ge 3 ] && [ "$n" -le 6 ] || ag_ok=0
  [ "$(grep -c "$m:begin" "$dest_ag/AGENTS.md")" -eq 1 ] || ag_ok=0
done
if [ "$ag_ok" -eq 1 ]; then
  record 0 "install: AGENTS.md blocks stay within 6 lines and re-run replaces them once"
else
  record 1 "install: AGENTS.md blocks stay within 6 lines and re-run replaces them once"
fi

# prefile_check.sh: hit and clean cases
PF="$ROOT/.claude/skills/contribution/scripts/prefile_check.sh"
pf_dir="$WORK/prefile"; mkdir -p "$pf_dir"
printf 'AKIA[0-9A-Z]{16}\nZZTOPSECRET\n' > "$pf_dir/.banlist.txt"
printf 'LOCALONLYNAME\n' > "$pf_dir/.banlist.local.txt"
pf() { printf '%s' "$1" > "$pf_dir/t"; printf '%s' "$2" > "$pf_dir/b"; BANLIST_DIR="$pf_dir" bash "$PF" "$pf_dir/t" "$pf_dir/b" >/dev/null 2>&1; }
if pf "Generalized lesson" "Mention protocol/perun only."; then record 0 "prefile: clean draft passes"; else record 1 "prefile: clean draft passes"; fi
for c in "ZZTOPSECRET here" "LOCALONLYNAME here" "see acme/widgets repo" "tracked as #12345" "at /Users/jane/proj"; do
  if pf "t" "$c"; then record 1 "prefile: refuses '$c'"; else record 0 "prefile: refuses '$c'"; fi
done
rm "$pf_dir/.banlist.txt"
if pf "t" "clean"; then record 1 "prefile: missing banlist fails closed"; else record 0 "prefile: missing banlist fails closed"; fi

# pipe_mask_guard (#1328): gate|tail without pipefail warns/blocks; pipefail and unrelated pipes pass.
pmg="$ROOT/.claude/skills/agentic-delivery/scripts/pipe_mask_guard.py"
pmg_run() { printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "$1" | python3 "$pmg"; }
pmg_blk=0
printf '{"tool_input":{"command":"make test | tail"}}' | PIPE_MASK_MODE=block python3 "$pmg" >/dev/null 2>&1 || pmg_blk=$?
if pmg_run 'git push origin x 2>&1 | tail -5' | grep -q additionalContext \
   && ! pmg_run 'set -o pipefail; git push origin x | tail -5' | grep -q . \
   && ! pmg_run 'bash gate.sh | tee /tmp/g; echo ${PIPESTATUS[0]}' | grep -q . \
   && ! pmg_run 'ls | grep foo' | grep -q . \
   && ! pmg_run 'git push || tail x' | grep -q . \
   && ! printf 'not json' | python3 "$pmg" | grep -q . \
   && [ "$pmg_blk" -eq 2 ]; then
  record 0 "pipe_mask_guard: gate|tail warns/blocks; pipefail, PIPESTATUS, unrelated pipe, || pass"
else
  record 1 "pipe_mask_guard: gate|tail warns/blocks; pipefail, PIPESTATUS, unrelated pipe, || pass"
fi

# heavy_gate + session_brief (fleet enforcement): injected load/RAM/leases and git fixtures; report-only hooks.
hg="$ROOT/.claude/skills/agentic-delivery/scripts/heavy_gate.py"
sbr="$ROOT/.claude/skills/agentic-delivery/scripts/session_brief.py"
hg_dir="$(mktemp -d "${TMPDIR:-/tmp}/hg.XXXXXX")"
hg_run() { printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "$1" \
  | PERUN_POLICY="$hg_dir/pol.json" PERUN_HEAVY_DIR="$hg_dir/leases" PERUN_GATE_CORES=8 "${@:2}" python3 "$hg"; }
echo '{}' >"$hg_dir/pol.json"; mkdir -p "$hg_dir/leases" "$hg_dir/busy"
printf '%s %s\n' "$$" "$(date +%s)" >"$hg_dir/busy/$$"; printf '%s %s\n' "$PPID" "$(date +%s)" >"$hg_dir/busy/$PPID"
hg_t0=$(python3 -c 'import time;print(time.time())')
hg_ok=1
hg_run 'cd x && npm test' env PERUN_GATE_LOAD1=20 PERUN_GATE_FREE_RAM_PCT=60 | grep -q '"deny".*machine busy (load 20.0/8' || { hg_ok=0; echo "hg: load-high not blocked"; }
hg_run 'pytest -q' env PERUN_GATE_LOAD1=1 PERUN_GATE_FREE_RAM_PCT=5 | grep -q 'low-ram' || { hg_ok=0; echo "hg: low-ram not blocked"; }
hg_run 'pytest -q' env PERUN_GATE_LOAD1=7 PERUN_GATE_FREE_RAM_PCT=60 PERUN_HEAVY_DIR="$hg_dir/busy" | grep -q 'heavy-lease-full 2/2' || { hg_ok=0; echo "hg: full lease not blocked"; }
echo '{"local_cpu": "maximize"}' >"$hg_dir/max.json"
[ -z "$(hg_run 'pytest -q' env PERUN_GATE_LOAD1=7 PERUN_GATE_FREE_RAM_PCT=60 PERUN_HEAVY_DIR="$hg_dir/busy" PERUN_POLICY="$hg_dir/max.json")" ] || { hg_ok=0; echo "hg: maximize did not raise slots"; }
[ -z "$(hg_run 'npm run build' env PERUN_GATE_LOAD1=1 PERUN_GATE_FREE_RAM_PCT=60)" ] || { hg_ok=0; echo "hg: idle host blocked"; }
[ -z "$(hg_run 'git commit -m fix-pytest-flake && grep jest x' env PERUN_GATE_LOAD1=99 PERUN_GATE_FREE_RAM_PCT=1)" ] || { hg_ok=0; echo "hg: non-heavy command blocked"; }
[ -z "$(hg_run 'make check' env PERUN_GATE_LOAD1=99 PERUN_HEAVY_PATTERNS='make check\b' PERUN_GATE_FREE_RAM_PCT=60 | grep -v deny)" ] \
  && hg_run 'make check' env PERUN_GATE_LOAD1=99 PERUN_HEAVY_PATTERNS='make check\b' PERUN_GATE_FREE_RAM_PCT=60 | grep -q deny || { hg_ok=0; echo "hg: custom pattern ignored"; }
[ -z "$(printf 'not json' | python3 "$hg")" ] || { hg_ok=0; echo "hg: garbage stdin not allowed"; }
echo '{not json' >"$hg_dir/bad.json"
hg_run 'pytest' env PERUN_GATE_LOAD1=99 PERUN_GATE_FREE_RAM_PCT=60 PERUN_POLICY="$hg_dir/bad.json" | grep -q '"deny".*machine busy' || { hg_ok=0; echo "hg: bad policy file did not fall back to default policy and still gate"; }
printf '{"tool_input":{"command":"pytest"}}' | bash -c 'python3 "$1" || true' _ "$hg_dir/missing.py" 2>/dev/null; [ $? -eq 0 ] || { hg_ok=0; echo "hg: missing hook file did not fail open"; }
hg_ms=$(python3 -c "import time,subprocess;t=time.time();subprocess.run(['python3','$hg'],input=b'{\"tool_input\":{\"command\":\"pytest\"}}',capture_output=True);print(int((time.time()-t)*1000))")
[ "$hg_ms" -lt 200 ] || { hg_ok=0; echo "hg: slow (${hg_ms}ms)"; }
# session_brief: git fixture with one merged worktree, a PRIORITIES.md, a stale installed version.
sb_src="$hg_dir/src"; sb_repo="$hg_dir/repo"; mkdir -p "$sb_src/.claude/skills/deep-code-review"
git -C "$sb_src" init -q -b main && echo 9.9.9 >"$sb_src/.claude/skills/deep-code-review/VERSION" \
  && git -C "$sb_src" add -A && git -C "$sb_src" -c user.name=t -c user.email=t@example.com commit -qm v \
  && git -C "$sb_src" update-ref refs/remotes/origin/main HEAD
git clone -q "$sb_src" "$sb_repo" && echo 1.0.0 >"$sb_repo/.claude/skills/deep-code-review/VERSION" \
  && git -C "$sb_repo" worktree add -q -b done-lane "$hg_dir/wt/done" origin/main 2>/dev/null \
  && printf '# P\n1. #42 Fix the importer\n2. #7 Other\n' >"$sb_repo/PRIORITIES.md"
sb_out=$(cd "$sb_repo" && echo '{}' | PERUN_SOURCE="$sb_src" CLAUDE_PROJECT_DIR="$sb_repo" python3 "$sbr" | python3 -c 'import json,sys;print(json.load(sys.stdin)["systemMessage"])')
[ "$(printf '%s\n' "$sb_out" | wc -l)" -le 3 ] \
  && printf '%s' "$sb_out" | grep -q "perun 1.0.0 < 9.9.9.*update-installed.sh" \
  && printf '%s' "$sb_out" | grep -q "1 worktree(s) merged into origin/main.*clean_finished.sh" \
  && printf '%s' "$sb_out" | grep -q "#42 Fix the importer" || { hg_ok=0; echo "sb: brief wrong: $sb_out"; }
# outside a repo: no report lines (systemMessage); only the always-on HOST_RULES additionalContext may print.
[ "$(cd "$hg_dir" && echo x | PERUN_SOURCE=/nonexistent CLAUDE_PROJECT_DIR="$hg_dir/none" python3 "$sbr" | python3 -c 'import json,sys;d=json.load(sys.stdin);print("systemMessage" in d)')" = False ] || { hg_ok=0; echo "sb: noisy outside a repo"; }
# report-only: no hook file may delete or stop anything.
if grep -nE '\brm[[:space:]]|\bkill\b|pkill|worktree[[:space:]",]+remove|rmtree|os\.(remove|unlink|kill)|find .*-delete|\.unlink\(' "$hg" "$sbr"; then
  hg_ok=0; echo "hooks contain a delete/kill call"
fi
if [ "$hg_ok" = 1 ]; then
  record 0 "heavy_gate/session_brief: load/RAM/lease blocks, maximize, fail-open, <200ms (${hg_ms}ms), <=3-line brief, no delete/kill"
else
  record 1 "heavy_gate/session_brief: load/RAM/lease blocks, maximize, fail-open, <200ms, <=3-line brief, no delete/kill"
fi

# vacuous_test_gate + preflight: planted-RED selftests (vacuous/skipped specs FAIL, missing = COULD_NOT_CHECK;
# all cheap gates run, unstartable gate = COULD_NOT_RUN).
for sc in vacuous_test_gate preflight session_brief; do
  if python3 "$ROOT/.claude/skills/agentic-delivery/scripts/$sc.py" --selftest >/dev/null 2>&1; then
    record 0 "$sc: --selftest passes"
  else
    record 1 "$sc: --selftest passes"
  fi
done

# escaped_defects --gh (#1331): an empty --since is an empty search term; must not query gh.
ed="$ROOT/.claude/skills/agentic-delivery/scripts/escaped_defects.py"
if python3 -c "import sys; sys.path.insert(0,'$(dirname "$ed")'); import escaped_defects as e; assert e.gh_escaped('', None) is None and e.gh_escaped('  ', None) is None"; then
  record 0 "escaped_defects: empty gh search term returns None"
else
  record 1 "escaped_defects: empty gh search term returns None"
fi

# finding_ground_check.py + merge_findings.py: grounding and merge gates behave (plain-assert suite).
if python3 "$ROOT/scripts/test_finding_gates.py" >/dev/null; then
  record 0 "finding gates: ground check + merge/dedupe/cap tests pass"
else
  record 1 "finding gates: ground check + merge/dedupe/cap tests pass"
fi

# /perun-run command: exists, has frontmatter, names the drain test it depends on.
if head -1 "$ROOT/commands/perun-run.md" | grep -q '^---$' \
  && grep -q 'description:' "$ROOT/commands/perun-run.md" \
  && grep -q 'next --check' "$ROOT/commands/perun-run.md"; then
  record 0 "perun-run command: frontmatter and next --check present"
else
  record 1 "perun-run command: frontmatter and next --check present"
fi

# ---------------------------------------------------------------------------
# rules — rule-enforcement lint: planted RED, advisory/mechanism/baseline pass,
# baseline growth needs a commit marker. Own git fixture.
# ---------------------------------------------------------------------------
# dirty-tree guard lint: a skill shell script that runs `git checkout|switch|reset` on a caller-given
# tree must call require_clean_tree (agentic-delivery/scripts/_dirty_guard.sh) so it refuses a dirty
# tree up front instead of silently wiping uncommitted edits.
# ---------------------------------------------------------------------------
_dg_bad() { # file...: print each whose first git checkout/switch/reset (comments ignored) is not preceded by a require_clean_tree call line
  local f
  for f in "$@"; do
    awk -v F="$f" '
      /^[[:space:]]*#/ { next }
      /^[[:space:]]*require_clean_tree([[:space:]]|$)/ { g = 1 }
      !g && /(^|[^[:alnum:]_.-])git( +(-[cC] +("[^"]*"|[^ ]+)|--[a-z-]+(=[^ ]+)?|-[a-z]))* +(checkout|switch|reset)([[:space:]]|$)/ { print F; exit }' "$f"
  done
  return 0
}
_dg_fix="$WORK/dg-fixture.sh"
printf 'git checkout -q --detach "$X"\n' >"$_dg_fix"
[ -n "$(_dg_bad "$_dg_fix")" ]; record $? "dirty-tree lint: a checkout script without the guard is flagged"
printf '# require_clean_tree\ngit -c a=b --git-dir=.g reset --hard\n' >"$_dg_fix"
[ -n "$(_dg_bad "$_dg_fix")" ]; record $? "dirty-tree lint: a comment mention and git -c/--git-dir forms do not pass"
printf 'git -C "a b" switch x\n' >"$_dg_fix"
[ -n "$(_dg_bad "$_dg_fix")" ]; record $? "dirty-tree lint: quoted git -C path form is flagged"
printf 'require_clean_tree . || exit 2\ngit checkout -q --detach "$X"\n' >"$_dg_fix"
[ -z "$(_dg_bad "$_dg_fix")" ]; record $? "dirty-tree lint: a guarded checkout script passes"
_dg_real=$(_dg_bad "$ROOT"/.claude/skills/*/scripts/*.sh)
if [ -z "$_dg_real" ]; then record 0 "dirty-tree lint: every skill script with checkout/switch/reset calls require_clean_tree"
else printf '  unguarded: %s\n' "$_dg_real"; record 1 "dirty-tree lint: every skill script with checkout/switch/reset calls require_clean_tree"; fi

# ---------------------------------------------------------------------------
rr="$WORK/rules-fixture"
mkdir -p "$rr/.claude/skills/demo" "$rr/scripts"
git -C "$rr" init -q
git -C "$rr" config user.email "test@example.com"
git -C "$rr" config user.name "Test"
printf '# Demo\n\nYou MUST run scripts/check.sh before merge.\n\nThis is advisory: NEVER ship on Friday.\n\n```\nALWAYS in a fence is skipped\n```\n\n  ```\n  NEVER in an indented fence is skipped\n  ```\n\nMUST-LOAD is a budget term.\n' \
  >"$rr/.claude/skills/demo/SKILL.md"
: >"$rr/scripts/rule-enforcement-baseline.tsv"
git -C "$rr" add -A >/dev/null 2>&1
git -C "$rr" commit -qm base >/dev/null 2>&1
rbase="$(git -C "$rr" rev-parse HEAD)"
rb="$rr/scripts/rule-enforcement-baseline.tsv"

gate "$GATES" rules --baseline "$rb" --base "$rbase" "$rr"
if [ "$GATE_RC" -eq 0 ] && grep -q '^rules: ok (0 ' "$WORK/last.log"; then
  record 0 "rules: mechanism-named, advisory, fenced and MUST-LOAD lines are not flagged"
else
  record 1 "rules: mechanism-named, advisory, fenced and MUST-LOAD lines are not flagged"
fi

printf '\nYou ALWAYS keep the tone calm.\n' >>"$rr/.claude/skills/demo/SKILL.md"
gate "$GATES" rules --baseline "$rb" "$rr"
if [ "$GATE_RC" -ne 0 ] && grep -q 'RULE UNENFORCED (new)' "$WORK/last.log" && grep -q 'keep the tone calm' "$WORK/last.log"; then
  record 0 "rules: FIRES on a new unenforced hard rule and names it (planted RED)"
else
  record 1 "rules: FIRES on a new unenforced hard rule and names it (planted RED)"
fi

gate "$GATES" rules --list "$rr"
bash "$GATES" rules --list "$rr" >"$rb"
git -C "$rr" add -A >/dev/null 2>&1
git -C "$rr" commit -qm "grow baseline" >/dev/null 2>&1
gate "$GATES" rules --baseline "$rb" "$rr"
rc_plain=$GATE_RC
gate "$GATES" rules --baseline "$rb" --base "$rbase" "$rr"
if [ "$rc_plain" -eq 0 ] && [ "$GATE_RC" -ne 0 ] && grep -q 'rule-baseline-raise' "$WORK/last.log"; then
  record 0 "rules: baselined rule passes, but baseline growth vs base FIRES without a marker (planted RED)"
else
  record 1 "rules: baselined rule passes, but baseline growth vs base FIRES without a marker (planted RED)"
fi

git -C "$rr" commit -q --allow-empty -m "x" -m "rule-baseline-raise: tone rule is advisory prose" >/dev/null 2>&1
gate "$GATES" rules --baseline "$rb" --base "$rbase" "$rr"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "rules: baseline growth with a rule-baseline-raise marker passes"
else
  record 1 "rules: baseline growth with a rule-baseline-raise marker passes"
fi

gate "$GATES" rules --baseline "$WORK/nope.tsv" "$rr"
if [ "$GATE_RC" -ne 0 ]; then
  record 0 "rules: missing baseline fails closed"
else
  record 1 "rules: missing baseline fails closed"
fi

gate "$GATES" rules --baseline "$ROOT/scripts/rule-enforcement-baseline.tsv" "$ROOT"
if [ "$GATE_RC" -eq 0 ]; then
  record 0 "rules: the real repo has no new unenforced hard rule"
else
  record 1 "rules: the real repo has no new unenforced hard rule"
fi

# partition_diff: deterministic whole-file diff split; selftest covers byte-for-byte reproduction,
# line accounting, odd paths, CRLF, empty/malformed input.
if python3 "$ROOT/.claude/skills/deep-code-review/scripts/partition_diff.py" --selftest >/dev/null 2>&1; then
  record 0 "partition_diff: --selftest passes"
else
  record 1 "partition_diff: --selftest passes"
fi

# context_nudge / lane_resume_nudge: advisory cost hooks; selftests cover thresholds, growth stamp, overlap, fail-open.
for nudge in context_nudge lane_resume_nudge; do
  if python3 "$ROOT/.claude/skills/agentic-delivery/scripts/$nudge.py" --selftest >/dev/null 2>&1; then
    record 0 "$nudge: --selftest passes"
  else
    record 1 "$nudge: --selftest passes"
  fi
done
# the operating-layer template wires both hooks
if grep -q 'context_nudge.py' "$ROOT/.claude/skills/agentic-delivery/templates/operating-layer.settings.json" \
   && grep -q 'lane_resume_nudge.py' "$ROOT/.claude/skills/agentic-delivery/templates/operating-layer.settings.json"; then
  record 0 "operating-layer template wires context_nudge + lane_resume_nudge"
else
  record 1 "operating-layer template wires context_nudge + lane_resume_nudge"
fi

# ===========================================================================
# drive-to-goal: the rule, both spend modes, and the override knob live once in
# the lane preamble; operating-discipline.md keeps the first rule and points at
# it (and the perun-run override stays). Waste-filter wording: test_max_pace_no_waste.py.
_dtg=1
_lp=.claude/skills/agentic-delivery/templates/lane-preamble.md
_od=.claude/skills/agentic-delivery/references/operating-discipline.md
grep -qF 'Drive to the goal (first rule)' "$ROOT/$_lp" \
  && grep -qF 'Default: be cautious about spend and report spend to the owner' "$ROOT/$_lp" \
  && grep -qF 'Maximum pace:' "$ROOT/$_lp" \
  && grep -qF 'do not pause for approval inside any granted budget' "$ROOT/$_lp" \
  && grep -qF 'set tokens maximize' "$ROOT/$_lp" \
  && grep -qF 'counts as the grant for the human-gate push' "$ROOT/$_lp" \
  && grep -qF 'Drive to the goal (first rule)' "$ROOT/$_od" \
  && grep -qF '`templates/lane-preamble.md` **Drive to the goal**' "$ROOT/$_od" || _dtg=0
grep -qF 'is such a grant for push and merge only' "$ROOT/commands/perun-run.md" || _dtg=0
if [ "$_dtg" -eq 1 ]; then record 0 "drive-to-goal: rule, two spend modes and override present"; else record 1 "drive-to-goal: rule, two spend modes and override present"; fi

# hermeticity sentinel (own lane, appended at the end by convention): nothing
# above wrote outside $WORK. A regression here means some case dropped a
# fixture into the real checkout instead of $WORK — exactly the kind of
# shared-state leak that makes concurrent copies of this suite (parallel
# worktrees/lanes on one host) corrupt one another instead of running
# hermetically side by side.
# ===========================================================================
if [ "$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)" = "$_root_sentinel" ]; then
  record 0 "hermetic: suite writes nothing outside its run root ($WORK)"
else
  record 1 "hermetic: suite writes nothing outside its run root ($WORK)"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
