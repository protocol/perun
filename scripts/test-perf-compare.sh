#!/usr/bin/env bash
# Tests for perf_compare.sh: refusals, verdict math, the detached base worktree and its cleanup (other worktrees and hooks left
# alone), argv and path quoting through sh and dash, a missing hyperfine, and (when hyperfine is installed) one real run. A fake
# hyperfine on PATH writes canned schema-2 exports, so the math is exact and nothing is timed. Everything lives in a throwaway git
# repo under $TMPDIR; no network, nothing is pushed or fetched.
# shellcheck disable=SC2319 # each `ok $?` reads the status of the [ ] check on the line before it, on purpose
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
S="$ROOT/.claude/skills/deep-code-review/scripts/perf_compare.sh"
T="$(mktemp -d "${TMPDIR:-/tmp}/pc.XXXXXX")" || exit 1; trap 'rm -rf "$T"' EXIT
fails=0; n=0
ok() { n=$((n+1)); if [ "$1" = 0 ]; then :; else fails=$((fails+1)); echo "FAIL: $2"; fi; }

# --- hermetic git: no inherited repo, config or identity ---
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_CEILING_DIRECTORIES="$T"
export GIT_AUTHOR_NAME="Jane Smith" GIT_AUTHOR_EMAIL="jane@example.com" GIT_COMMITTER_NAME="Jane Smith" GIT_COMMITTER_EMAIL="jane@example.com"
mkdir "$T/fake" "$T/gitbin" "$T/home" "$T/tmpd"
printf '#!/bin/sh\nexec "%s" "$@"\n' "$(command -v git)" >"$T/gitbin/git"; chmod +x "$T/gitbin/git"

# --- fake hyperfine 2.x: logs argv and the worktree list, runs each timed command once, writes a canned schema-2 export ---
cat >"$T/fake/hyperfine" <<'EOF'
#!/bin/sh
echo "$@" >>"$HF_LOG"
git worktree list >>"$HF_WT"
[ -n "${HF_KILL:-}" ] && { kill -TERM "$PPID"; exit 0; }
c1=; c2=; j=
while [ $# -gt 0 ]; do
  case "$1" in
    --export-json) j="$2"; shift 2 ;;
    --style|--warmup|--runs|-n) shift 2 ;;
    --*) shift ;;
    *) if [ -z "$c1" ]; then c1="$1"; else c2="$1"; fi; shift ;;
  esac
done
${HF_SH:-sh} -c "$c1" >>"$HF_RUNS" 2>&1 && ${HF_SH:-sh} -c "$c2" >>"$HF_RUNS" 2>&1 || { echo "Error: Command terminated with non-zero exit code" >&2; exit 1; }
[ -n "${HF_GARBAGE:-}" ] && { echo "not json" >"$j"; exit 0; }
set -- $HF_MEANS
printf '{"schema_version":%s,"results":[{"name":"base","summary":{"time_wall_clock":{"unit":"second","count":%s,"mean":%s,"stddev":%s}}},{"name":"current","summary":{"time_wall_clock":{"unit":"second","count":%s,"mean":%s,"stddev":%s}}}]}\n' "${HF_SCHEMA:-2}" "${HF_N:-10}" "$1" "$2" "${HF_N:-10}" "$3" "$4" >"$j"
EOF
chmod +x "$T/fake/hyperfine"
export HF_LOG="$T/hf.log" HF_WT="$T/hf.wt" HF_RUNS="$T/hf.runs" HF_MEANS="0.100 0.002 0.103 0.002" HF_N=10

# --- repo: commit 1 = origin/main ("base-version"), commit 2 = HEAD ("mid-version"), working tree = "current-version" ---
R="$T/repo"; git init -q -b main "$R"
( cd "$R" && echo base-version >v.txt && mkdir sub && echo s >sub/s.txt && git add . && git commit -qm base && git update-ref refs/remotes/origin/main HEAD \
  && echo mid-version >v.txt && git commit -qam mid )
echo current-version >"$R/v.txt"
R2="$T/repo2"; git init -q -b main "$R2"; ( cd "$R2" && echo x >f && git add f && git commit -qm one )   # no origin/main
mkdir "$R/newdir"                                                                                      # untracked: absent at any base

run() { env HOME="$T/home" TMPDIR="$T/tmpd" PATH="${P:-$T/fake:$T/gitbin:/usr/bin:/bin}" "$@"; }
pc() { run "$BASH" "$S" "$@"; }
reset() { : >"$HF_LOG"; : >"$HF_WT"; : >"$HF_RUNS"; unset HF_GARBAGE HF_SCHEMA HF_KILL HF_SH; export HF_MEANS="0.100 0.002 0.103 0.002" HF_N=10; }
nwt() { git -C "${1:-$R}" worktree list | wc -l | tr -d ' '; }
clean() { [ "$(nwt)" = 1 ] && [ -z "$(ls -A "$T/tmpd")" ]; }   # no base worktree registered, no temp dir left
refused() { # refused DESC args...: exit 2, empty stdout, REFUSED on stderr (naming $WANT when set), hyperfine never called
  d="$1"; shift; reset; out="$(cd "${DIR:-$R}" && pc "$@" 2>"$T/err")"; rc=$?
  [ $rc -eq 2 ] && [ -z "$out" ] && grep -q "^REFUSED.*${WANT:-}" "$T/err" && [ ! -s "$HF_LOG" ]; ok $? "refuse $d (rc=$rc)"
}

# --- help and refusals ---
reset; out="$(cd "$T/home" && pc --help)"; rc=$?
[ $rc -eq 0 ] && [ "$out" = "usage: perf_compare.sh [--runs N] [--base REF] [--json FILE] -- CMD..." ]; ok $? "--help prints usage, exit 0, from anywhere"
refused "no --" --runs 3
refused "empty command" --
refused "unknown flag" --nope -- true
refused "bare command without --" true
for r in 0 1 abc -3 1.5 10000 ""; do WANT="--runs" refused "--runs '$r'" --runs "$r" -- true; done
WANT="--runs needs" refused "--runs without a value" --runs
WANT="--base needs" refused "--base without a value" --base
WANT="not an option" refused "--base --evil" --base --evil -- true
WANT="not a commit" refused "--base unknown ref" --base nosuchref -- true
WANT="--base REF" DIR="$R2" refused "no origin/main and no --base" -- true
WANT="not inside a git work tree" DIR="$T/home" refused "outside a repository" -- true
clean; ok $? "refusals leave no worktree and no temp dir"

# --- missing hyperfine: visible, non-zero, nothing on stdout, nothing created ---
if ! PATH=/usr/bin:/bin command -v hyperfine >/dev/null; then
  reset; out="$(cd "$R" && P="$T/gitbin:/usr/bin:/bin" pc --base HEAD -- true 2>"$T/err")"; rc=$?
  [ $rc -eq 1 ] && [ -z "$out" ] && grep -q '^NOT CHECKED: hyperfine (install: brew install hyperfine)$' "$T/err" && clean; ok $? "missing hyperfine: NOT CHECKED on stderr, exit 1, empty stdout, nothing created (rc=$rc)"
else
  echo "SKIP: missing-hyperfine case (a hyperfine sits in /usr/bin:/bin)"
fi

# --- verdict math: ranges are mean +- sd and overlap when the means differ by at most sd + sd ---
J="$T/out.json"
vline() { reset; rm -f "$J"; export HF_MEANS="$1"; out="$(cd "$R" && pc --base HEAD --json "$J" -- true 2>"$T/err")"; rc=$?; }
vline "0.100 0.002 0.103 0.002"
[ $rc -eq 0 ] && [ "$out" = "perf_compare: base 100.00 ms (sd 2.00, n=10) | current 103.00 ms (sd 2.00, n=10) | ratio 1.03x | within noise (ranges overlap) | json=$J" ]; ok $? "overlapping ranges: within noise, means, sd, ratio, n ($out)"
vline "0.5 0.125 0.75 0.125"
[ $rc -eq 0 ] && [ "$out" = "perf_compare: base 500.00 ms (sd 125.00, n=10) | current 750.00 ms (sd 125.00, n=10) | ratio 1.50x | within noise (ranges overlap) | json=$J" ]; ok $? "ranges that just touch (gap = sd + sd) count as overlap ($out)"
vline "0.5 0.125 0.751 0.125"
case "$out" in *"| ratio 1.50x | slower (ranges do not overlap) | json=$J") rc2=0 ;; *) rc2=1 ;; esac; [ $rc -eq 0 ] && [ $rc2 -eq 0 ]; ok $? "a hair past the touch point: slower ($out)"
vline "0.100 0.002 0.150 0.002"
case "$out" in *"| ratio 1.50x | slower (ranges do not overlap) | json=$J") rc2=0 ;; *) rc2=1 ;; esac; [ $rc -eq 0 ] && [ $rc2 -eq 0 ]; ok $? "clear gap, current larger: slower, ratio current/base ($out)"
vline "0.150 0.002 0.100 0.002"
case "$out" in *"| ratio 0.67x | faster (ranges do not overlap) | json=$J") rc2=0 ;; *) rc2=1 ;; esac; [ $rc -eq 0 ] && [ $rc2 -eq 0 ]; ok $? "clear gap, current smaller: faster ($out)"
vline "0.100 0 0.100 0"
case "$out" in *"| ratio 1.00x | within noise (ranges overlap) | json=$J") rc2=0 ;; *) rc2=1 ;; esac; [ $rc -eq 0 ] && [ $rc2 -eq 0 ]; ok $? "zero spread and equal means: within noise ($out)"
vline "0.100 0 0.101 0"
case "$out" in *"| slower (ranges do not overlap) | json=$J") rc2=0 ;; *) rc2=1 ;; esac; [ $rc -eq 0 ] && [ $rc2 -eq 0 ]; ok $? "zero spread, any gap: slower ($out)"
[ -z "$(cat "$T/err")" ] && [ "$(printf '%s\n' "$out" | wc -l | tr -d ' ')" = 1 ]; ok $? "stdout is exactly one verdict line, nothing on stderr"
python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["schema_version"]==2 and d["results"][1]["summary"]["time_wall_clock"]["mean"]==0.101, d' "$J"; ok $? "--json FILE holds the raw hyperfine export"
clean; ok $? "success: base worktree removed and temp dir gone"

# --- a bad export is a failure, never a verdict, and leaves no JSON behind ---
reset; rm -f "$J"; export HF_SCHEMA=1; out="$(cd "$R" && pc --base HEAD --json "$J" -- true 2>"$T/err")"; rc=$?
[ $rc -eq 1 ] && [ -z "$out" ] && grep -q 'unsupported hyperfine export' "$T/err" && [ ! -e "$J" ] && clean; ok $? "schema_version 1: unsupported, exit 1, no JSON (rc=$rc)"
reset; rm -f "$J"; export HF_GARBAGE=1; out="$(cd "$R" && pc --base HEAD --json "$J" -- true 2>"$T/err")"; rc=$?
[ $rc -eq 1 ] && [ -z "$out" ] && grep -q 'unreadable hyperfine export' "$T/err" && [ ! -e "$J" ] && clean; ok $? "unparseable export: exit 1, no JSON (rc=$rc)"
reset; rm -f "$J"; out="$(cd "$R" && pc --base HEAD --json "$T/nodir/x.json" -- true 2>"$T/err")"; rc=$?
[ $rc -eq 1 ] && [ -z "$out" ] && grep -q 'cannot write' "$T/err" && clean; ok $? "unwritable --json path: exit 1, no verdict (rc=$rc)"

# --- a failing command, and a TERM mid-run, still remove the base worktree and temp dir ---
reset; rm -f "$J"; out="$(cd "$R" && pc --base HEAD --json "$J" -- false 2>"$T/err")"; rc=$?
[ $rc -eq 1 ] && [ -z "$out" ] && grep -q 'hyperfine failed; CMD must exit 0 in both trees' "$T/err" && [ ! -e "$J" ] && clean; ok $? "CMD failing in a tree: exit 1, no JSON, cleaned up (rc=$rc)"
reset; export HF_KILL=1; out="$(cd "$R" && pc --base HEAD --json "$J" -- true 2>"$T/err")"; rc=$?
[ $rc -eq 143 ] && [ -z "$out" ] && [ ! -e "$J" ] && clean; ok $? "TERM during the run: exit 143, worktree and temp dir removed (rc=$rc)"

# --- what hyperfine is given: a detached base worktree, the working tree, and the flags ---
reset; out="$(cd "$R" && pc --base HEAD -- cat v.txt 2>"$T/err")"; rc=$?
[ "$(cat "$HF_RUNS")" = "$(printf 'mid-version\ncurrent-version')" ]; ok $? "--base HEAD: base runs the committed file, current the working-tree edit"
[ "$(wc -l <"$HF_WT" | tr -d ' ')" = 2 ] && sed -n 2p "$HF_WT" | grep -q '(detached HEAD)$'; ok $? "during the run a second, detached worktree is registered"
grep -qF -e '--style none --shell=default --warmup 1 --runs 10 --export-json' "$HF_LOG" && grep -q -e '-n base cd ' "$HF_LOG" && grep -q -e '-n current cd ' "$HF_LOG"; ok $? "hyperfine flags: --style none --shell=default --warmup 1 --runs 10, names base and current"
reset; out="$(cd "$R" && pc --runs 7 -- cat v.txt 2>"$T/err")"; rc=$?
[ "$(cat "$HF_RUNS")" = "$(printf 'base-version\ncurrent-version')" ] && grep -qF -e '--runs 7' "$HF_LOG"; ok $? "default base is the merge-base with origin/main; --runs 7 reaches hyperfine"
[ -f "$R/.git/perf-compare-last.json" ]; ok $? "default JSON lands in <git-common-dir>/perf-compare-last.json"
reset; out="$(cd "$R" && pc --base HEAD -- printf '%s|' 'a b' c 2>"$T/err")"
[ "$(cat "$HF_RUNS")" = 'a b|c|a b|c|' ]; ok $? "several words after --: argv preserved (a quoted word with a space stays one argument)"
reset; out="$(cd "$R" && pc --base HEAD -- 'echo x | tr x y' 2>"$T/err")"
[ "$(cat "$HF_RUNS")" = "$(printf 'y\ny')" ]; ok $? "one word after --: a shell string (a pipe works)"
reset; out="$(cd "$R/sub" && pc --base HEAD -- pwd 2>"$T/err")"
case "$(sed -n 1p "$HF_RUNS")" in */base/sub) a=0 ;; *) a=1 ;; esac; [ $a -eq 0 ] && [ "$(sed -n 2p "$HF_RUNS")" = "$R/sub" ]; ok $? "run from a subdirectory: the same subdirectory of the base tree and of the current tree"
reset; out="$(cd "$R/newdir" && pc --base HEAD -- true 2>"$T/err")"; rc=$?
[ $rc -eq 1 ] && grep -q 'newdir/ does not exist at' "$T/err" && [ ! -s "$HF_LOG" ] && clean; ok $? "directory absent at the base: exit 1, hyperfine not run, cleaned up (rc=$rc)"

# --- the caller's repo is left alone: no global worktree prune on exit, no hooks run for the temporary checkout ---
git -C "$R" worktree add -q --detach "$T/stale" HEAD && mv "$T/stale" "$T/stale.gone"
reset; out="$(cd "$R" && pc --base HEAD -- true 2>"$T/err")"; rc=$?
[ $rc -eq 0 ] && [ "$(nwt)" = 2 ] && git -C "$R" worktree list | grep -q prunable; ok $? "a stale worktree entry of the caller (directory gone) is still listed prunable after a run (rc=$rc)"
git -C "$R" worktree prune
mkdir "$T/hooks"; printf '#!/bin/sh\ntouch "%s"\n' "$T/hook.ran" >"$T/hooks/post-checkout"; chmod +x "$T/hooks/post-checkout"
git -C "$R" config core.hooksPath "$T/hooks"
git -C "$R" worktree add -q --detach "$T/ctl" HEAD; [ -e "$T/hook.ran" ]; ok $? "control: the post-checkout hook fires on a plain worktree add"
git -C "$R" worktree remove --force "$T/ctl"; rm -f "$T/hook.ran"
reset; out="$(cd "$R" && pc --base HEAD -- true 2>"$T/err")"; rc=$?
[ $rc -eq 0 ] && [ ! -e "$T/hook.ran" ] && clean; ok $? "a core.hooksPath post-checkout hook never runs for the temporary checkout (rc=$rc)"
git -C "$R" config --unset core.hooksPath

# --- argv and both cd paths reach the shell intact: POSIX single quotes, not printf %q ($'..' for control characters, which dash reads as a literal $) ---
# shellcheck disable=SC2016,SC1003 # literal $, backtick and backslash arguments, on purpose
args=('a b' "it's" 'say "hi"' '$HOME' '`id`' $'x\ty' $'l1\nl2' $'end\n' '' '*' '\')
want="$(printf '%s|' "${args[@]}")"
W=$'sp ace\'q"d$HOME`id`\ttab\nnl'
R4="$T/repo4"; git init -q -b main "$R4"; ( cd "$R4" && mkdir "$W" && echo w >"$W/w" && git add . && git commit -qm w )
for hs in sh dash; do
  if [ "$hs" = dash ]; then hs="$(command -v dash)" || { echo "SKIP: dash round trip (dash is not installed)"; continue; }; fi
  reset; export HF_SH="$hs"; out="$(cd "$R" && pc --base HEAD -- printf '%s|' "${args[@]}" 2>"$T/err")"; rc=$?
  [ $rc -eq 0 ] && [ "$(cat "$HF_RUNS")" = "$want$want" ]; ok $? "args with space ' \" \$ backtick tab newline round-trip via $hs (rc=$rc: $(cat "$HF_RUNS"))"
  reset; export HF_SH="$hs"; out="$(cd "$R4/$W" && pc --base HEAD -- pwd 2>"$T/err")"; rc=$?
  case "$(cat "$HF_RUNS")" in *"/base/$W"$'\n'"$R4/$W") a=0 ;; *) a=1 ;; esac; [ $rc -eq 0 ] && [ $a -eq 0 ]; ok $? "cd paths with space ' \" \$ backtick tab newline round-trip via $hs (rc=$rc: $(cat "$HF_RUNS"))"
done
[ "$(nwt "$R4")" = 1 ] && [ -z "$(ls -A "$T/tmpd")" ]; ok $? "quoting runs: worktree and temp dir removed"

# --- one real hyperfine run: 0.01 s vs 0.3 s of sleep reads slower; skipped visibly when hyperfine is not installed ---
hf="$(command -v hyperfine 2>/dev/null)"
if [ -n "$hf" ]; then
  R3="$T/repo3"; git init -q -b main "$R3"; ( cd "$R3" && echo 0.01 >d.txt && git add d.txt && git commit -qm base ); echo 0.3 >"$R3/d.txt"
  # shellcheck disable=SC2016 # $(cat d.txt) expands in the child shell, on purpose
  out="$(cd "$R3" && P="$(dirname "$hf"):$T/gitbin:/usr/bin:/bin" pc --runs 3 --base HEAD --json "$T/real.json" -- 'sleep $(cat d.txt)' 2>"$T/err")"; rc=$?
  case "$out" in "perf_compare: base "*"| slower (ranges do not overlap) | json=$T/real.json") a=0 ;; *) a=1 ;; esac
  [ $rc -eq 0 ] && [ $a -eq 0 ]; ok $? "real hyperfine: slower verdict ($out; $(cat "$T/err"))"
  python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["schema_version"]==2 and [r["name"] for r in d["results"]]==["base","current"], d' "$T/real.json"; ok $? "real hyperfine export: schema 2, base then current"
  [ "$(nwt "$R3")" = 1 ] && [ -z "$(ls -A "$T/tmpd")" ]; ok $? "real run: worktree and temp dir removed"
else
  echo "SKIP: real hyperfine run (hyperfine is not installed)"
fi

if [ $fails -eq 0 ]; then echo "perf_compare: $n/$n"; else echo "perf_compare: $((n-fails))/$n"; exit 1; fi
