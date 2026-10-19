#!/usr/bin/env bash
# reap_own.sh — kill your own dev servers older than MAX_AGE_S whose cwd is under ROOT (your own lane or
# session tree). Never kills by name alone: a process must be owned by the current user AND have its cwd
# under ROOT, so other lanes' and other users' servers are untouchable. Safe to run on every tick.
# A kill is verified: SIGTERM, wait up to KILL_WAIT_S (default 5) polling kill -0, then SIGKILL; a process still
# alive after that is not counted as reaped (a warning goes to stderr). Prints "reaped=N".
#
# Env: ROOT (required, absolute dir), PATTERN (pgrep -f regex, default 'next-server|next dev'),
# KEEP (optional dir under ROOT whose servers are spared), MAX_AGE_S (default 7200: idle for 2 hours),
# QA_PORTS (optional space-separated TCP ports: an own listener there with cwd under ROOT is reaped too,
# since a leftover server on a QA port makes the QA script skip its browser half), KILL_WAIT_S.
#
# --report: cross-session, read-only, never kills. Lists every own process matching PATTERN or listening on a
# TCP port as "<cwd> pid=<n> age=<s>s" sorted by worktree path (ROOT optional: unset = all of them), then
# "orphans=N", the free RAM, and a "FINDING hot" line for each own process using >= CPU_HOT percent CPU
# (default 50) for more than MAX_AGE_S. Use it as the hand-back check (ROOT=<lane worktree>: orphans=0 means no
# server or listener is left under it) and as the coordinator-wake check. When pgrep/lsof fail or a live pid's cwd
# is unreadable it prints "orphans=COULD_NOT_CHECK" and exits 2, never a false "orphans=0"; the kill mode likewise prints "reaped=COULD_NOT_CHECK" (exit 2).
set -euo pipefail
WAIT=${KILL_WAIT_S:-5}
alive() { kill -0 "$1" 2>/dev/null && [ "$(ps -o stat= -p "$1" 2>/dev/null | cut -c1)" != Z ]; }
age() { { ps -o etime= -p "$1" 2>/dev/null || true; } | tr -d ' ' | awk -F'[-:]' '{n=NF; s=$n+60*$(n-1); if(n>=3)s+=3600*$(n-2); if(n>=4)s+=86400*$(n-3); print s}'; }
kill_verified() {
  local i; kill "$1" 2>/dev/null || true
  for ((i = 0; i < WAIT * 4; i++)); do alive "$1" || return 0; sleep 0.25; done
  kill -9 "$1" 2>/dev/null || true; sleep 0.2
  if alive "$1"; then echo "WARN: pid $1 survived SIGKILL" >&2; return 1; fi
}
[ -z "${REAP_OWN_SOURCE_ONLY:-}" ] || return 0  # run_ledger.sh sources the helpers above (alive, age, kill_verified) and nothing else
REPORT=0; [ "${1:-}" = "--report" ] && REPORT=1
if [ $REPORT = 1 ]; then ROOT=${ROOT:-}; else : "${ROOT:?set ROOT to your own tree}"; fi
[ -z "$ROOT" ] || ROOT=$(cd "$ROOT" && pwd -P)  # lsof reports resolved paths; a symlinked ROOT would match nothing
KEEP=${KEEP:+$(cd "$KEEP" && pwd -P)}; PATTERN=${PATTERN:-next-server|next dev}; KEEP=${KEEP:-}
MAX=${MAX_AGE_S:-7200}
prc=0; PIDS=$(pgrep -u "$(id -u)" -f "$PATTERN") || prc=$?; BAD=""  # rc 1 = no match; rc >= 2 = pgrep itself failed
[ "$prc" -le 1 ] || BAD="pgrep failed rc=$prc"
command -v lsof >/dev/null || BAD="${BAD:+$BAD; }lsof missing"
if [ $REPORT = 1 ]; then PIDS="$PIDS $(lsof -t -a -u "$(id -u)" -iTCP -sTCP:LISTEN 2>/dev/null || true)"; fi
for q in ${QA_PORTS:-}; do PIDS="$PIDS $(lsof -t -a -u "$(id -u)" -iTCP:"$q" -sTCP:LISTEN 2>/dev/null || true)"; done
n=0; rows=""
for P in $(printf '%s\n' $PIDS | sort -u); do
  [ "$P" != "$$" ] || continue
  lo=$(lsof -a -p "$P" -d cwd -Fn 2>/dev/null) || true  # lsof rc 1 (pid gone / denied) must not abort under pipefail; an unreadable live cwd becomes BAD below
  C=$(sed -n 's/^n//p' <<<"$lo" | head -1)
  if [ -z "$C" ] && alive "$P"; then BAD="${BAD:+$BAD; }cwd of pid $P unreadable"; fi
  if [ -n "$ROOT" ]; then
    case "$C" in "$ROOT"|"$ROOT"/*) ;; *) continue ;; esac
  fi
  if [ -n "$KEEP" ]; then case "$C" in "${KEEP%/}"|"${KEEP%/}"/*) continue ;; esac; fi
  E=$(age "$P")
  if [ $REPORT = 1 ]; then rows="$rows$C pid=$P age=${E:-0}s"$'\n'; n=$((n+1)); continue; fi
  if [ "${E:-0}" -gt "$MAX" ]; then if kill_verified "$P"; then n=$((n+1)); fi; fi
done
if [ $REPORT = 0 ]; then
  [ -z "$BAD" ] || { echo "reaped=COULD_NOT_CHECK ($BAD); nothing known reaped" >&2; echo "reaped=COULD_NOT_CHECK"; exit 2; }
  echo "reaped=$n"; exit 0
fi
printf '%s' "$rows" | sort
if [ -n "$BAD" ]; then echo "orphans=COULD_NOT_CHECK ($BAD); not zero, not green" >&2; echo "orphans=COULD_NOT_CHECK"; exit 2; fi
echo "orphans=$n"
if [ -r /proc/meminfo ]; then echo "ram_free_mb=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)"
elif command -v vm_stat >/dev/null; then
  echo "ram_free_mb=$(vm_stat | awk '/page size of/{s=$8} /Pages (free|inactive)/{p+=$3} END{print int(p*s/1048576)}')"
fi
ps -u "$(id -u)" -o pid=,pcpu=,comm= | while read -r p c m; do
  [ "${c%.*}" -ge "${CPU_HOT:-50}" ] 2>/dev/null || continue
  e=$(age "$p"); if [ "${e:-0}" -gt "$MAX" ]; then echo "FINDING hot pid=$p cpu=$c% age=${e}s $m"; fi
done
