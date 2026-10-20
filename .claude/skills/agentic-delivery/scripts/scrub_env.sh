#!/usr/bin/env bash
# scrub_env.sh [cmd args...] — run a test command without inherited git/DB env.
#
# WHY: a hook runs with GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE set; a test's `git init` then inherited
# GIT_DIR and flipped the host repo to core.bare=true. Unsets every GIT_* var plus DATABASE_URL, PG*,
# MYSQL_* and REDIS_URL (a test must never reach a real DB). With a command: exec it with those unset.
# With no command: print the `-u NAME ...` args for use as `env $(scrub_env.sh) cmd`.
# SCRUB_PREFIXES (optional, space-separated, e.g. "RUNNER_ PERUN_MODE_"): also unset every var starting with one of
# them, so a runner's exported mode switch cannot leak into the tests it runs and fake a red base branch.
args=()
for n in $(compgen -e); do
  case "$n" in GIT_*|DATABASE_URL|PG*|MYSQL_*|REDIS_URL) args+=(-u "$n"); continue ;; esac
  for p in ${SCRUB_PREFIXES:-}; do case "$n" in "$p"*) args+=(-u "$n"); break ;; esac; done
done
if [ $# -gt 0 ]; then exec env ${args[@]+"${args[@]}"} "$@"; fi
echo ${args[@]+"${args[@]}"}
