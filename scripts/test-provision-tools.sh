#!/usr/bin/env bash
# provision_tools.sh (dry run, --print, --cache) and how review_checks.sh uses the offline caches it warms: the osv-scanner offline DB,
# a local semgrep p/default snapshot, ~/.local/bin, the closing "ran X / wired Y" line with its record (partial scopes, scanners provisioning
# cannot install) and the printed owner line run end to end against stubs. Hermetic: the scripts run
# under env -i with a PATH of wrappers for system tools plus stub scanners (no scanner installed on this host can be found), a throwaway
# HOME, cache root and ~/.local/bin. Nothing is installed or downloaded.
# shellcheck disable=SC2088
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
S=$ROOT/.claude/skills/deep-code-review/scripts
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-prov.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap '[ -n "$T" ] && rm -rf "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
BASH_BIN=$(type -P bash)
ALL="gitleaks semgrep trivy osv-scanner actionlint zizmor bandit scorecard gosec grype checkov hadolint"
mkdir "$T/farm" "$T/ub" "$T/tmp" "$T/proj"
for c in awk bash basename cat chmod cp cut date dirname env find git grep gtimeout head jq ls mkdir mktemp mv nice paste perl python3 readlink rm sed sleep sort tail tee timeout tr uname uniq wc xargs; do
  p=$(type -P "$c") || continue
  printf '#!/bin/sh\nexec %s "$@"\n' "$p" >"$T/farm/$c"; chmod +x "$T/farm/$c"
done
stubs() { local d t; d=$(mktemp -d "$T/st.XXXXXX"); for t in "$@"; do printf '#!/bin/sh\nexit 0\n' >"$d/$t"; chmod +x "$d/$t"; done; echo "$d"; }
# run [VAR=val ...] CMD...: PA (a dir of stubs) comes first on PATH, then the wrappers; caches and ~/.local/bin are throwaway dirs.
run() { env -i PATH="${PA:+$PA:}$T/farm" HOME="$T/home" TMPDIR="$T/tmp" DCR_CACHE_ROOT="$T/cache" DCR_USER_BIN="$T/ub" "$@"; }
PT() { run "$BASH_BIN" "$S/provision_tools.sh" "$@"; }
warm_trivy() { mkdir -p "$T/cache/trivy/db"; echo x >"$T/cache/trivy/db/trivy.db"; }
warm_osv() { mkdir -p "$T/cache/osv-scalibr/npm"; echo x >"$T/cache/osv-scalibr/npm/all.zip"; }
warm_sg() { mkdir -p "$T/cache/dcr-tools/semgrep"; echo 'rules: []' >"$T/cache/dcr-tools/semgrep/p-default.yml"; }
cd "$T/proj"; PHYS=$(pwd -P); q() { printf '%q' "$1"; }

# 1. dry run: lists every missing tool and cold cache, exits 0, writes nothing
PA=; rc=0; o=$(PT 2>&1) || rc=$?
[ "$rc" = 0 ] && [ "$(grep -c '^MISSING ' <<<"$o")" = 12 ] && grep -q 'COLD     trivy DB' <<<"$o" && grep -q 'COLD     osv-scanner offline DB' <<<"$o" \
  && grep -q 'COLD     semgrep p/default snapshot' <<<"$o" && grep -q '12 missing, 3 cold; nothing was installed' <<<"$o" && ok "dry run lists 12 missing, 3 cold" || { bad "dry run"; echo "$o"; }
[ ! -e "$T/cache" ] && [ ! -e "$T/home" ] && ok "dry run writes nothing" || bad "dry run wrote"

# 2. --print: exactly one stdout line with the whole fix; the listing goes to stderr
PA=; o=$(PT --print 2>"$T/e")
[ "$(wc -l <<<"$o")" -eq 1 ] && ! grep -q 'MISSING' <<<"$o" && grep -q 'MISSING  gitleaks' "$T/e" && ok "--print: one stdout line, listing on stderr" || { bad "--print shape"; echo "$o"; }
for want in "brew install pipx gitleaks trivy osv-scanner actionlint scorecard gosec grype hadolint" \
  "pipx install semgrep==1.182.1; pipx install zizmor==1.31.1; pipx install bandit==1.9.4; pipx install checkov==3.4.0" \
  'mkdir -p '"$(q "$T/cache/dcr-tools/docker-config-empty")"' && DOCKER_CONFIG='"$(q "$T/cache/dcr-tools/docker-config-empty")"' trivy --cache-dir '"$(q "$T/cache/trivy")"' fs --download-db-only' \
  "OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$(q "$T/cache") osv-scanner --offline-vulnerabilities --download-offline-databases $(q "$PHYS")" \
  "curl -fsSL https://semgrep.dev/c/p/default -o $(q "$T/cache/dcr-tools/semgrep/p-default.yml.part") && mv " ; do
  grep -qF -- "$want" <<<"$o" && ok "--print has: ${want:0:60}" || { bad "--print lacks: $want"; echo "$o"; }
done
grep -qE '; bash [^ ]*/provision_tools\.sh$' <<<"$o" && ok "--print ends with a re-check of this script" || bad "--print re-check"

# 3. present tools and warm caches are left out; pipx present means no `brew install pipx`
PA=$(stubs gitleaks trivy semgrep pipx); warm_trivy
o=$(PT --print 2>/dev/null)
grep -qF "brew install osv-scanner actionlint scorecard gosec grype hadolint; pipx install zizmor==1.31.1" <<<"$o" && ! grep -q 'semgrep==\|download-db-only' <<<"$o" && ok "--print omits present tools and the warm trivy DB" || { bad "partial"; echo "$o"; }
: >"$T/cache/trivy/db/trivy.db"; o=$(PT --print 2>/dev/null); grep -q 'download-db-only' <<<"$o" && ok "an empty trivy.db is cold" || bad "empty db warm"

# 4. a tool only in ~/.local/bin (pipx, uv tool) counts as installed; DCR_USER_BIN= (empty) turns that off
printf '#!/bin/sh\n' >"$T/ub/zizmor"; chmod +x "$T/ub/zizmor"
o=$(PT 2>&1); grep -qF "ok       zizmor ($T/ub/zizmor, not on PATH" <<<"$o" && ok "dry run: zizmor installed, not on PATH" || { bad "not on PATH note"; echo "$o"; }
o=$(PT --print 2>/dev/null); ! grep -q 'zizmor==' <<<"$o" && ok "--print skips a tool found in ~/.local/bin" || bad "~/.local/bin tool still in the install line"
o=$(run DCR_USER_BIN= "$BASH_BIN" "$S/provision_tools.sh" 2>&1); grep -q 'MISSING  zizmor' <<<"$o" && ok "empty DCR_USER_BIN: not probed" || bad "empty DCR_USER_BIN"
rm "$T/ub/zizmor"

# 5. all present and warm: nothing to provision; a DIR argument re-emits the osv download for that dir
PA=$(stubs $ALL pipx); warm_trivy; warm_osv; warm_sg
o=$(PT --print 2>/dev/null); [ "$o" = "# nothing to provision" ] && ok "all present + warm: nothing to provision" || { bad "nothing to provision"; echo "$o"; }
mkdir "$T/other"; o=$(PT --print "$T/other" 2>/dev/null)
grep -qF -- "--download-offline-databases $(q "$T/other")" <<<"$o" && ok "DIR argument re-emits the osv download" || { bad "DIR argument"; echo "$o"; }
rc=0; PT "$T/none" >/dev/null 2>&1 || rc=$?; [ "$rc" = 2 ] && ok "bad DIR: exit 2" || bad "bad DIR rc=$rc"
rc=0; PT --bogus >/dev/null 2>&1 || rc=$?; [ "$rc" = 2 ] && ok "unknown flag: exit 2" || bad "bogus rc=$rc"

# 6. --cache NAME: prints the location and exits 0 when warm, prints nothing and exits 1 when cold
for kv in "trivy:$T/cache/trivy" "osv:$T/cache" "semgrep:$T/cache/dcr-tools/semgrep/p-default.yml"; do
  n=${kv%%:*}; o=$(PT --cache "$n"); [ "$o" = "${kv#*:}" ] && ok "--cache $n warm -> its path" || bad "--cache $n warm: $o"
done
mv "$T/cache" "$T/cache.warm"
for n in trivy osv semgrep; do rc=0; o=$(PT --cache "$n") || rc=$?; [ "$rc" = 1 ] && [ -z "$o" ] && ok "--cache $n cold -> exit 1, silent" || bad "--cache $n cold rc=$rc"; done
rc=0; PT --cache bogus >/dev/null 2>&1 || rc=$?; [ "$rc" = 2 ] && ok "--cache bogus: exit 2" || bad "--cache bogus rc=$rc"
mkdir -p "$T/odb/osv-scanner/npm"; echo x >"$T/odb/osv-scanner/npm/all.zip"
o=$(run REVIEW_OSV_DB_DIR="$T/odb" "$BASH_BIN" "$S/provision_tools.sh" --cache osv); [ "$o" = "$T/odb" ] && ok "REVIEW_OSV_DB_DIR wins, legacy osv-scanner/ layout counts" || bad "osv override: $o"
mkdir -p "$T/ptc/db"; echo x >"$T/ptc/db/trivy.db"
o=$(run REVIEW_TRIVY_CACHE="$T/ptc" TRIVY_CACHE_DIR="$T/none" "$BASH_BIN" "$S/provision_tools.sh" --cache trivy); [ "$o" = "$T/ptc" ] && ok "REVIEW_TRIVY_CACHE beats TRIVY_CACHE_DIR" || bad "trivy override: $o"

# 7. review_checks.sh on stub scanners: caches decide the osv-scanner mode and the semgrep config
SCN=$(mktemp -d "$T/scn.XXXXXX"); PA=$SCN; LOG=$T/log; export HUB_LOG=
cat >"$SCN/osv-scanner" <<X
#!/bin/sh
echo "osv \$* DIR=\${OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY:-}" >>$LOG
case "\$*" in *--download-offline-databases*) mkdir -p "\$OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY/osv-scalibr/npm"; echo x >"\$OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY/osv-scalibr/npm/all.zip"; exit 0 ;; esac
[ -z "\${OSV_RC:-}" ] || { echo "\${OSV_MSG:-}" >&2; exit "\$OSV_RC"; }
echo '{"results":[]}'
X
cat >"$SCN/semgrep" <<X
#!/bin/sh
echo "semgrep \$*" >>$LOG
case "\$*" in *p/default*) [ -z "\${SG_FAIL:-}" ] || exit 2 ;; esac
echo "{\"results\":[\${SG_ROW:-}],\"errors\":[\${SG_ERR:-}]}"
X
# trivy: --download-db-only warms the --cache-dir (else TRIVY_CACHE_DIR, else ~/.cache/trivy); TV_NEEDDB: a scan without a DB there fails;
# TV_BUNDLE: a scan with the misconfig scanner cannot reach the check bundle
cat >"$SCN/trivy" <<X
#!/bin/sh
echo "trivy \$*" >>$LOG
d=\${TRIVY_CACHE_DIR:-\$HOME/.cache/trivy}; p=
for a in "\$@"; do [ "\$p" != --cache-dir ] || d=\$a; p=\$a; done
case "\$*" in *--download-db-only*) mkdir -p "\$d/db"; echo x >"\$d/db/trivy.db"; exit 0 ;; esac
[ -z "\${TV_NEEDDB:-}" ] || [ -s "\$d/db/trivy.db" ] || { echo "FATAL vulnerability db is missing in \$d" >&2; exit 1; }
case "\$*" in *misconfig*) [ -z "\${TV_BUNDLE:-}" ] || { echo "FATAL check bundle: dial check.trivy.dev blocked" >&2; exit 1; } ;; esac
echo '{"Results":[]}'
X
printf '#!/bin/sh\ncase "$*" in *--log-opts*) exit "${GL_HIST_RC:-0}" ;; esac\nexit 0\n' >"$SCN/gitleaks"; chmod +x "$SCN"/*
R=$T/repo; mkdir "$R"; cd "$R"; RP=$(pwd -P); git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base && git branch base
echo 'x = 1' >app.js; printf '{"lockfileVersion":3,"packages":{}}' >package-lock.json; git add . && git -c user.email=t@example.com -c user.name=t commit -q -m files
RCX=() # extra review_checks.sh arguments
rc_run() { : >"$LOG"; run PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 "$@" "$BASH_BIN" "$S/review_checks.sh" --base base ${RCX[@]+"${RCX[@]}"} >"$T/out" 2>"$T/err" || true; }
e() { grep -qF -- "$1" "$T/err"; }
st() { jq -e "$1" "$R/.git/review-checks-last.json" >/dev/null; }
WIRED='["gitleaks","semgrep","trivy","osv-scanner"]'

rc_run # cold caches: osv-scanner stays opt-in, semgrep asks the registry for p/default, and the gap is named
! grep -q '^osv ' "$LOG" && e "osv-scanner (REVIEW_OSV not set" && e "osv-scanner (warm the offline DB: provision_tools.sh --print)" && grep -q 'semgrep .*--config p/default' "$LOG" \
  && ok "cold: osv-scanner not run, p/default from the registry, gap named" || { bad "cold run"; cat "$T/err" "$LOG"; }
e "review_checks: ran 3 / wired 4 scanners; not run: osv-scanner; fixable: osv-scanner (run: bash $S/provision_tools.sh --print $(q "$RP"))" && ok "cold: ran 3 / wired 4, fixable osv-scanner, its command names this repo as DIR" || { bad "cold summary"; cat "$T/err"; }
st ".wired == $WIRED and .not_run == [\"osv-scanner\"] and .fixable == [\"osv-scanner\"] and (.ts | type) == \"number\"" && ok "cold: record written to the git common dir" || { bad "cold record"; cat "$R/.git/review-checks-last.json"; }

warm_osv; rc_run # warm osv DB: offline run, no REVIEW_OSV needed
grep -qx "osv --offline-vulnerabilities --format json -L ./package-lock.json DIR=$T/cache" "$LOG" && ! e "REVIEW_OSV not set" && ok "warm osv cache: --offline-vulnerabilities with the cache dir" || { bad "warm osv"; cat "$LOG" "$T/err"; }
e "review_checks: ran 4 / wired 4 scanners" && ! e "fixable:" && st '.not_run == [] and .fixable == []' && ok "warm: ran 4 / wired 4, nothing fixable" || { bad "warm summary"; cat "$T/err"; }
rc_run REVIEW_OSV=1; grep -qx "osv --format json -L ./package-lock.json DIR=" "$LOG" && ok "REVIEW_OSV=1 keeps the online API mode" || { bad "REVIEW_OSV=1"; cat "$LOG"; }
rc_run REVIEW_OSV_DB_DIR="$T/emptydb"; ! grep -q '^osv ' "$LOG" && e "NOT CHECKED: no pre-seeded DB in REVIEW_OSV_DB_DIR=$T/emptydb" && ok "an explicit empty REVIEW_OSV_DB_DIR beats a warm cache" || { bad "explicit db"; cat "$T/err"; }
rc_run REVIEW_OSV_DB_DIR="$T/odb"; grep -q "DIR=$T/odb\$" "$LOG" && ok "an explicit warm REVIEW_OSV_DB_DIR is used as is" || { bad "explicit warm db"; cat "$LOG"; }
rc_run OSV_RC=127 OSV_MSG="unable to fetch OSV database: no offline version of the OSV database is available"
e "osv-scanner (no offline DB for the ecosystem of package-lock.json: run bash $S/provision_tools.sh --print $RP)" && ok "a missing ecosystem DB names the fix" || { bad "127 hint"; cat "$T/err"; }
e "fixable: osv-scanner (run: bash $S/provision_tools.sh --print $(q "$RP"))" || { bad "127 closing line lacks DIR"; cat "$T/err"; }
cmd=$(sed -n 's/.*(run: \(.*\))$/\1/p' "$T/err" | tail -n1); o=$(run "$BASH_BIN" -c "$cmd" 2>/dev/null) # npm's zip is warm, so a bare --print would print no osv download
grep -qF -- "--download-offline-databases $(q "$RP")" <<<"$o" && ok "the closing-line command re-emits the osv download for this repo" || { bad "closing-line command prints no osv download"; echo "$o"; }

warm_sg; rc_run # snapshot replaces the registry pack with a local file
grep -q "semgrep .*--config $T/cache/dcr-tools/semgrep/p-default.yml" "$LOG" && ! grep -q 'semgrep .*p/default ' "$LOG" && ok "semgrep snapshot is a local --config" || { bad "snapshot"; cat "$LOG"; }
rc_run REVIEW_SEMGREP_REGISTRY=0; ! grep -q 'p-default.yml\|p/default' "$LOG" && ok "REVIEW_SEMGREP_REGISTRY=0 drops both" || bad "registry off"
rm "$T/cache/dcr-tools/semgrep/p-default.yml"; rc_run SG_FAIL=1 # registry unreachable and no snapshot: bundled rules rerun; the gap is reported once (not-run line naming the fix), partial and fixable
[ "$(grep -c '^semgrep ' "$LOG")" = 2 ] && e "not run: semgrep p/default pack (exit 2); bundled rules only (warm a local snapshot: bash $S/provision_tools.sh --print)" \
  && e "partial: semgrep(bundled-only); fixable: semgrep (run: bash $S/provision_tools.sh --print)" && ! e "missing tools: semgrep" \
  && ok "semgrep fallback: reported once with the fix, counted partial and fixable" || { bad "semgrep fallback"; cat "$LOG" "$T/err"; }

mv "$SCN/osv-scanner" "$T/ub/osv-scanner"; rc_run # a scanner only in ~/.local/bin is found (DCR_USER_BIN is that dir here)
grep -q '^osv --offline' "$LOG" && ok "review_checks.sh adds ~/.local/bin to PATH" || { bad "~/.local/bin on PATH"; cat "$T/err"; }
rc_run DCR_USER_BIN=; ! grep -q '^osv ' "$LOG" && e "osv-scanner" && e "not run: osv-scanner" && ok "empty DCR_USER_BIN: osv-scanner not found, reported not run" || { bad "empty DCR_USER_BIN"; cat "$T/err"; }

mkdir -p .github/workflows; echo 'on: push' >.github/workflows/ci.yml; git add . && git -c user.email=t@example.com -c user.name=t commit -q -m wf
mv "$T/ub/osv-scanner" "$SCN/osv-scanner"; rc_run # hub tools with work but not installed are wired, not run, fixable
e "NOT CHECKED: zizmor" && e "NOT CHECKED: actionlint" && e "ran 4 / wired 6 scanners; not run: zizmor, actionlint; fixable: zizmor, actionlint" && st '.fixable == ["zizmor", "actionlint"] and (.wired | index("zizmor"))' && ok "hub tools missing (workflow file routes zizmor and actionlint): wired 6, not run, fixable" || { bad "hub summary"; cat "$T/err"; }

# 7b. fresh repos: trivy's cache dir, secret-only and partial runs, scanners provisioning cannot install, the owner line end to end
mkrepo() { R=$T/$1; mkdir "$R"; cd "$R"; RP=$(pwd -P); git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base && git branch base; }
commit() { git add . && git -c user.email=t@example.com -c user.name=t commit -q -m files; }
mkrepo repo2; echo 'x = 1' >app.js; printf '{"lockfileVersion":3,"packages":{}}' >package-lock.json; commit
PA=$SCN; warm_osv

rc_run # a cold trivy cache: trivy's own default dir, no --cache-dir
! grep -q '^trivy .*--cache-dir' "$LOG" && ok "cold trivy cache: no --cache-dir" || { bad "cold trivy args"; cat "$LOG"; }
warm_trivy; rc_run # DCR_CACHE_ROOT moves the warmed cache off trivy's default dir, so it must be passed
grep -q "^trivy .* --cache-dir $T/cache/trivy --scanners vuln,misconfig " "$LOG" && ok "a warm trivy cache is passed as --cache-dir" || { bad "warm trivy cache not passed"; cat "$LOG"; }
rc_run REVIEW_TRIVY_CACHE="$T/mine"
grep -q "^trivy .* --cache-dir $T/mine --scanners" "$LOG" && ! grep -q -- "--cache-dir $T/cache/trivy" "$LOG" && ok "REVIEW_TRIVY_CACHE still wins" || { bad "REVIEW_TRIVY_CACHE"; cat "$LOG"; }

rc_run TV_BUNDLE=1 # the misconfig bundle is unreachable: the secret-only retry ran, a partial scope and never a full run
e "review_checks: trivy: secret-only (misconfig bundle unreachable)" && e "review_checks: ran 4 / wired 4 scanners; partial: trivy(secret-only)" && ! e "fixable:" \
  && st '.partial == ["trivy(secret-only)"] and .not_run == [] and .fixable == []' && ok "trivy secret-only: listed as partial, in the record" || { bad "secret-only"; cat "$T/err" "$R/.git/review-checks-last.json"; }
rc_run; e "ran 4 / wired 4 scanners" && ! e "partial:" && st '.partial == []' && ok "a full run lists nothing partial" || { bad "full run"; cat "$T/err"; }

SGR='{"path":"app.js","start":{"line":1},"check_id":"x.y","extra":{"message":"m"}}'
rc_run SG_ROW="$SGR" SG_ERR='{"message":"boom"}' # findings plus errors: it ran, with a partial scope
e "review_checks: partial: semgrep ran but reported errors" && e "review_checks: ran 4 / wired 4 scanners; partial: semgrep(errors)" && st '.partial == ["semgrep(errors)"] and .not_run == []' \
  && ok "semgrep with errors and findings: ran, partial" || { bad "partial semgrep"; cat "$T/err"; }
rc_run SG_ERR='{"message":"boom"}' # errors and no findings: nothing usable was scanned
e "not run: semgrep (scan errored, no findings)" && st '.not_run == ["semgrep"] and .partial == []' && ok "semgrep with errors and no findings: not run, not partial" || { bad "errored semgrep"; cat "$T/err"; }

# shellcheck, ruff and the history scan count as wired, but provision_tools.sh cannot install them: not run, never fixable
mkrepo repo3; echo 'echo hi' >t.sh; echo 'x = 1' >t.py; commit
SX=$(mktemp -d "$T/sx.XXXXXX"); printf '#!/bin/sh\nexit "${LINT_RC:-0}"\n' >"$SX/shellcheck"; cp "$SX/shellcheck" "$SX/ruff"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[]}'" >"$SX/bandit"; chmod +x "$SX"/* # bandit: the hub tool a .py file wires
RCX=(--history); PA=$SX:$SCN; rc_run LINT_RC=2 GL_HIST_RC=2
e "review_checks: ran 4 / wired 7 scanners; not run: gitleaks-history, shellcheck, ruff" && ! e "fixable:" \
  && st '(.wired | length) == 7 and (.not_run | sort) == ["gitleaks-history","ruff","shellcheck"] and .fixable == []' && ok "failed shellcheck, ruff and history scans: wired, not run, never fixable" || { bad "failed lint scans"; cat "$T/err"; }
rc_run; e "review_checks: ran 7 / wired 7 scanners" && st '.not_run == [] and .fixable == []' && ok "healthy shellcheck, ruff and history scans: ran 7 / wired 7" || { bad "healthy lint scans"; cat "$T/err"; }
SXR=$(mktemp -d "$T/sxr.XXXXXX"); cp "$SX/ruff" "$SX/bandit" "$SXR"/; PA=$SXR:$SCN; rc_run
e "review_checks: ran 6 / wired 7 scanners; not run: shellcheck" && ! e "fixable:" && st '.not_run == ["shellcheck"] and .fixable == []' && ok "shellcheck not installed: not run, not fixable" || { bad "no shellcheck"; cat "$T/err"; }
RCX=(); PA=$SCN

# the owner line end to end: a cold cache root, run the printed command and line (stub brew, pipx, curl, trivy, osv-scanner), then every wired scanner runs
R=$T/repo2; cd "$R"; RP=$(pwd -P); C2=$T/c2; PE=$(mktemp -d "$T/pe.XXXXXX"); cp "$SCN"/* "$PE"/; PL=$T/prov.log; : >"$PL"
for t in brew pipx; do printf '#!/bin/sh\necho "%s $*" >>%s\n' "$t" "$PL" >"$PE/$t"; done
printf '#!/bin/sh\np=; for a in "$@"; do [ "$p" != -o ] || echo "rules: []" >"$a"; p=$a; done\n' >"$PE/curl"; chmod +x "$PE"/*
PA=$PE; rc_run DCR_CACHE_ROOT="$C2" TV_NEEDDB=1
st '.not_run == ["trivy","osv-scanner"] and .fixable == ["trivy","osv-scanner"]' && e "fixable: trivy, osv-scanner (run: bash $S/provision_tools.sh --print $(q "$RP"))" && ok "cold cache root: trivy and osv-scanner not run, fixable" || { bad "cold e2e"; cat "$T/err"; }
cmd=$(sed -n 's/.*(run: \(.*\))$/\1/p' "$T/err" | tail -n1); line=$(run DCR_CACHE_ROOT="$C2" "$BASH_BIN" -c "$cmd" 2>/dev/null)
run DCR_CACHE_ROOT="$C2" "$BASH_BIN" -c "$line" >"$T/prov.out" 2>&1 || true
cold=; for n in trivy osv semgrep; do run DCR_CACHE_ROOT="$C2" "$BASH_BIN" "$S/provision_tools.sh" --cache "$n" >/dev/null || cold+=" $n"; done
[ -z "$cold" ] && grep -qx 'pipx install zizmor==1.31.1' "$PL" && ok "the printed owner line installs and warms every cache" || { bad "owner line left cold:$cold"; cat "$T/prov.out" "$PL"; }
rc_run DCR_CACHE_ROOT="$C2" TV_NEEDDB=1 # trivy must find the DB the owner line warmed: no loop of NOT RUN after a provision
e "review_checks: ran 4 / wired 4 scanners" && ! e "fixable:" && st '.not_run == [] and .fixable == [] and .partial == []' && ok "after the owner line: ran 4 / wired 4, nothing fixable" || { bad "e2e re-run"; cat "$T/err"; }
PA=$SCN

# 8. the script is routed: full-map.md names it and tool-hub.md documents the owner line
RF=$ROOT/.claude/skills/deep-code-review/references
grep -q 'scripts/provision_tools.sh' "$RF/full-map.md" && grep -q 'provision_tools.sh --print' "$RF/tool-hub.md" && ok "routed from full-map.md, documented in tool-hub.md" || bad "provision_tools.sh not routed"
! grep -q 'exits 127' "$RF/tool-hub.md" && ok "tool-hub.md: no unsourced osv-scanner exit code" || bad "tool-hub.md claims 'exits 127'"
! grep -q 'osv-scanner stays behind' "$RF/tool-hub.md" && ! grep -q 'osv-scanner needs env' "$S/review_checks.sh" && ! grep -q 'only with .REVIEW_OSV=1' "$RF/method-situational.md" \
  && grep -q 'online only with .REVIEW_OSV=1' "$RF/tool-hub.md" && grep -q 'osv online with .REVIEW_OSV=1' "$RF/method-situational.md" && ok "osv-scanner docs: offline on a warm DB, online only with REVIEW_OSV=1" || bad "osv-scanner docs say it needs REVIEW_OSV=1"

# 9. CI children are hermetic: scrub_env.sh replaces both host knobs (an empty ~/.local/bin override, a throwaway cache root)
o=$(DCR_USER_BIN=/host/bin DCR_CACHE_ROOT=/host/cache "$BASH_BIN" "$ROOT/.claude/skills/agentic-delivery/scripts/scrub_env.sh" env)
grep -qx 'DCR_USER_BIN=' <<<"$o" && grep -q '^DCR_CACHE_ROOT=.*/cache$' <<<"$o" && ! grep -q '/host/' <<<"$o" && ok "scrub_env.sh pins DCR_USER_BIN and DCR_CACHE_ROOT" || bad "scrub_env.sh does not pin the provisioning knobs"

# 10. cleanup is the one guarded trap on the mktemp dir; any other recursive rm of a variable path in this file is a regression
[ "$(grep -cE '^[^#]*rm -rf? ' "$ROOT/scripts/$(basename "$0")")" = 1 ] && ok "one recursive rm: the guarded temp-dir trap" || bad "recursive rm outside the temp-dir trap"
exit $fail
