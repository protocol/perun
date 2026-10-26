# Sourced by train scripts. Process-table-free lock (no process-name matching, so wait chains cannot match each other):
#   lock_take <dir> [wait_secs=0] [timeout_min=30]  mkdir is the atomic claim; <dir>/pid and <dir>/ts record the holder.
#   <dir>/ts holds "<epoch> <hostname>". Returns 0 (held) or 1. A held lock whose holder looks stale (pid dead, or ts older than
#   timeout_min) is REPORTED with the exact command to clear it by hand and returns 1 at once; this file never moves or
#   deletes another owner's lock, EXCEPT under PERUN_CLAIM_REAP=enforce, which reaps a dead-pid claim recorded by this same
#   host (default `shadow`: only logs "SHADOW claim-reap: would reap ..."; `off`: silent). A claim with no host in its ts is never reaped.
#   A missing or empty pid/ts means the owner is mid-write: wait like any live holder. If this shell cannot write its own
#   record it removes only what it created (its own pid file) and returns 1.
#   lock_drop <dir>  releases it (only when this shell holds it).
_pid_live() { kill -0 "$1" 2>/dev/null || ps -p "$1" >/dev/null 2>&1; }  # kill -0 alone reads a live other-user pid (EPERM) as dead
_gdrop() { rm -f "$1/pid" "$1/ts"; rmdir "$1" 2>/dev/null; }  # release/break a reap guard dir
lock_take() {
  local d=$1 wait=${2:-0} tmo=${3:-30} p ts host rt=0 told= qn=${PERUN_QUEUE_NOTE_SECS:-120}
  [[ $qn =~ ^[0-9]+$ ]] && [ "$qn" -gt 0 ] || qn=120  # a bad PERUN_QUEUE_NOTE_SECS falls back to 120
  while :; do
    if mkdir "$d" 2>/dev/null; then
      { echo $$ >"$d/pid" && echo "$(date +%s) $(hostname -s)" >"$d/ts"; } 2>/dev/null && return 0
      echo "lock: cannot write owner record in $d" >&2; lock_drop "$d"; return 1
    fi
    p=$(cat "$d/pid" 2>/dev/null); ts=$(cat "$d/ts" 2>/dev/null) host=
    [[ $ts == *" "* ]] && { host=${ts#* }; ts=${ts%% *}; }  # ts file is "<epoch> <host>"; a bare epoch (old record) has no host
    if [[ $p =~ ^[0-9]+$ && $ts =~ ^[0-9]+$ ]]; then
      # Claim liveness: a dead pid recorded by THIS host (host recorded and equal) is reaped by whoever reads it.
      # PERUN_CLAIM_REAP=shadow (default) only logs the decision and keeps the report-only path; =enforce reaps; =off is silent.
      # Live = kill -0 succeeds OR ps -p finds it (kill -0 gives EPERM for a live pid owned by another user).
      if ! _pid_live "$p" && [ "${PERUN_CLAIM_REAP:-shadow}" != off ] && [ "$host" = "$(hostname -s)" ]; then
        if [ "${PERUN_CLAIM_REAP:-shadow}" = enforce ]; then
          # Reapers serialize on a guard dir ($d.reap, mkdir is atomic). A new locker cannot mkdir $d while the dead claim exists, so
          # the only race is reaper vs reaper, and the guard closes it: inside it, re-read the pid, re-check liveness, ONE atomic
          # rename to a unique tomb, drop the guard. No restore: a restore could land over a new holder's dir.
          # A guard is NEVER broken (any break races another reaper re-creating it): if the guard dir exists for any reason the
          # reap is skipped and the claim stays (fail closed). The guard's pid/ts are for the operator's log line only.
          # ponytail: a reaper crashed inside the guard leaves it until an operator removes it; flock would self-heal.
          local g="$d.reap" tomb="$d.reap.$$.$RANDOM$SECONDS"
          rt=$((rt + 1)); [ "$rt" -le 400 ] || { echo "claim-reap: gave up on $d after $rt tries" >&2; return 1; }  # bounds a rename failing for good
          if mkdir "$g" 2>/dev/null; then
            { echo $$ >"$g/pid" && echo "$(date +%s) $(hostname -s)" >"$g/ts"; } 2>/dev/null || { _gdrop "$g"; return 1; }
            if [ "$(cat "$d/pid" 2>/dev/null)" = "$p" ] && ! _pid_live "$p" && mv "$d" "$tomb" 2>/dev/null; then
              if [ "$(cat "$tomb/pid" 2>/dev/null)" = "$p" ]; then
                rm -f "$tomb/pid" "$tomb/ts"; rmdir "$tomb" 2>/dev/null
                echo "claim-reap: reaped $d (dead pid $p, same host)" >&2
              else
                _gdrop "$g"
                echo "claim-reap: LOST RACE, the claim moved to $tomb held pid '$(cat "$tomb/pid" 2>/dev/null)', not the dead pid $p; left there for hand review, not restored" >&2
                return 1
              fi
            fi
            _gdrop "$g"
          else
            echo "claim-reap: reap skipped: guard held ($g, recorded '$(cat "$g/pid" 2>/dev/null) $(cat "$g/ts" 2>/dev/null)'); claim $d left alone. If no reaper is running, clear the stale guard by hand: rm -f '$g/pid' '$g/ts'; rmdir '$g'" >&2
            return 1
          fi
          continue
        fi
        echo "SHADOW claim-reap: would reap $d (dead pid $p, same host); set PERUN_CLAIM_REAP=enforce to act" >&2
      fi
      if ! _pid_live "$p" || [ $(($(date +%s) - ts)) -gt $((tmo * 60)) ]; then
        echo "STALE-LOCK $d: holder pid $p looks dead or older than ${tmo}m; not touched. If it is not yours, clear by hand: rm -f '$d/pid' '$d/ts'; rmdir '$d'" >&2
        return 1
      fi
    fi
    local st=alive age=""
    if [[ $p =~ ^[0-9]+$ ]]; then _pid_live "$p" || st=dead; else st=unknown; fi
    [[ $ts =~ ^[0-9]+$ ]] && age=", age $(($(date +%s) - ts))s"
    [ "$wait" -gt 0 ] || { echo "lock held by pid ${p:-?} ($st$age) ($d)" >&2; return 1; }
    # first line at once, then one every PERUN_QUEUE_NOTE_SECS (default 120): a long wait is never silent
    [ -n "$told" ] && [ $((SECONDS - told)) -lt "$qn" ] || { echo "waiting on lock held by pid ${p:-?} ($st$age) ($d)" >&2; told=$SECONDS; }
    wait=$((wait - 1)); sleep 1
  done
}
lock_drop() {  # absent dir = nothing to drop; a dir this shell does not own is left alone and reported loudly (return 1)
  [ -d "$1" ] || return 0
  [ "$(cat "$1/pid" 2>/dev/null)" = $$ ] || { echo "lock_drop: $1 is not held by this shell (pid $$, holder '$(cat "$1/pid" 2>/dev/null)'); left in place" >&2; return 1; }
  rm -f "$1/pid" "$1/ts"; rmdir "$1" 2>/dev/null; return 0
}
