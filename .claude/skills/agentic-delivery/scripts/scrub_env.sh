#!/usr/bin/env bash
# scrub_env.sh [cmd args...] — run a test command without inherited git/DB env.
#
# WHY: a hook runs with GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE set; a test's `git init` then inherited
# GIT_DIR and flipped the host repo to core.bare=true. Unsets every GIT_* var plus DATABASE_URL, PG*,
# MYSQL_* and REDIS_URL (a test must never reach a real DB). With a command: exec it with those unset.
# With no command: print the `-u NAME ...` args for use as `env $(scrub_env.sh) cmd`.
# Also unsets the host-owned session env a test must not inherit: DBUS_*, XDG_RUNTIME_DIR, XDG_SESSION_*, INVOCATION_ID,
# JOURNAL_STREAM, NOTIFY_SOCKET (a systemd bus/unit a test would otherwise talk to).
# SCRUB_PREFIXES (optional, space-separated, e.g. "RUNNER_ PERUN_MODE_"): also unset every var starting with one of
# them, so a runner's exported mode switch cannot leak into the tests it runs and fake a red base branch.
# With a command it also isolates the child from the real GitHub account and network: invalid GH_TOKEN/GITHUB_TOKEN, an empty
# throwaway GH_CONFIG_DIR (no stored login), prompts off, and an unroutable proxy (127.0.0.1:9) so no child, even one that calls
# an absolute-path `gh` past a PATH stub, can post to a real PR (port 9 is the discard port: a connection is refused, not routed;
# loopback stays direct via NO_PROXY). Git-over-ssh is closed too: SSH_AUTH_SOCK unset, GIT_SSH_COMMAND=false, no global/system git
# config (so no credential helper), no askpass or terminal prompt. NOT covered: ~/.netrc, repo .env files and other file-based
# credentials a child reads by path. PERUN_ALLOW_NET=1 (a ci-test that truly needs the network exports it itself; it is logged to
# stderr) keeps the proxy vars as inherited but never the GitHub token, config dir or ssh/git-credential closures.
args=()
for n in $(compgen -e); do
  case "$n" in GIT_*|DATABASE_URL|PG*|MYSQL_*|REDIS_URL|DBUS_*|XDG_RUNTIME_DIR|XDG_SESSION_*|INVOCATION_ID|JOURNAL_STREAM|NOTIFY_SOCKET) args+=(-u "$n"); continue ;; esac
  for p in ${SCRUB_PREFIXES:-}; do case "$n" in "$p"*) args+=(-u "$n"); break ;; esac; done
done
if [ $# -gt 0 ]; then
  cfg=$(mktemp -d "${TMPDIR:-/tmp}/scrub-gh.XXXXXX") || exit 1
  trap 'rm -rf -- "$cfg"' EXIT
  net=(HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9 https_proxy=http://127.0.0.1:9 all_proxy=http://127.0.0.1:9 NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1)
  [ -z "${PERUN_ALLOW_NET:-}" ] || { net=(); echo "scrub_env: PERUN_ALLOW_NET set: proxy isolation off" >&2; }
  env ${args[@]+"${args[@]}"} -u GH_ENTERPRISE_TOKEN -u GITHUB_ENTERPRISE_TOKEN -u SSH_AUTH_SOCK GIT_SSH_COMMAND=false GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_ASKPASS=false GIT_TERMINAL_PROMPT=0 GH_TOKEN=invalid GITHUB_TOKEN=invalid GH_CONFIG_DIR="$cfg" GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1 ${net[@]+"${net[@]}"} "$@"
  exit $?
fi
echo ${args[@]+"${args[@]}"}
