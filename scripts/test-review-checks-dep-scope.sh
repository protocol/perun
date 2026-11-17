#!/usr/bin/env bash
# review_checks.sh dependency rows (osv-scanner, trivy; line 0): a row whose pkg@version is reachable only via
# devDependencies in its npm lockfile (package-lock v2/v3, yarn v1, pnpm v9) gets " (scope: dev)"; prod (also when
# shared with a dev path), devOptional, unknown package and unparseable lockfile stay untagged. Severity and row count
# never change. Stub scanners return fixed JSON for fictional acme-* packages; nothing is installed or fetched.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC=${RC_UNDER_TEST:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh} # override: run the test against another copy of the script
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-depscope.XXXXXX"); trap 'chmod -R u+w "$T"; rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin" "$T/repo"
unset REVIEW_OSV_DB_DIR REVIEW_TRIVY_CACHE OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY
stub() { printf '#!/usr/bin/env bash\n%s\n' "$2" >"$T/bin/$1"; chmod +x "$T/bin/$1"; }
# osv: the same five high advisories (one per acme package) for whichever lockfile is passed after -L
stub osv-scanner 'for a; do [ "$prev" = -L ] && f=${a#./}; prev=$a; done
vs() { printf "{\"package\":{\"name\":\"%s\",\"version\":\"1.0.0\"},\"vulnerabilities\":[{\"id\":\"GHSA-%s\",\"summary\":\"s\",\"database_specific\":{\"severity\":\"HIGH\"}}]}" "$1" "$1"; }
x=; case $f in scoped/*) x=,$(vs @acme/devtool);; esac
printf "{\"results\":[{\"source\":{\"path\":\"%s\"},\"packages\":[%s,%s,%s,%s,%s%s]}]}" "$f" "$(vs acme-prod)" "$(vs acme-dev)" "$(vs acme-shared)" "$(vs acme-opt)" "$(vs acme-devonly)" "$x"
exit 1'
stub trivy 'echo "{\"Results\":[{\"Target\":\"npm/package-lock.json\",\"Vulnerabilities\":[{\"VulnerabilityID\":\"CVE-T\",\"PkgName\":\"acme-dev\",\"InstalledVersion\":\"1.0.0\",\"Severity\":\"HIGH\",\"Title\":\"tt\"}]}]}"'
stub semgrep 'echo "{\"results\":[]}"'
cd "$T/repo"
git init -q . && g commit -q --allow-empty -m base && git branch base
mkdir npm yarn pnpm bad yres palias ws scoped yalias wsout shared ynr yurl
cat >npm/package-lock.json <<'J'
{"lockfileVersion":3,"packages":{"":{"name":"acme-app"},
"node_modules/acme-prod":{"version":"1.0.0"},
"node_modules/acme-dev":{"version":"1.0.0","dev":true},
"node_modules/acme-opt":{"version":"1.0.0","devOptional":true},
"node_modules/acme-shared":{"version":"1.0.0","dev":true},
"node_modules/acme-prod/node_modules/acme-shared":{"version":"1.0.0"}}}
J
echo '{"name":"acme-app","dependencies":{"acme-prod":"^1.0.0"},"devDependencies":{"acme-dev":"^1.0.0"}}' | tee yarn/package.json pnpm/package.json >/dev/null
cat >yarn/yarn.lock <<'J'
# yarn lockfile v1

acme-prod@^1.0.0:
  version "1.0.0"
  dependencies:
    acme-shared "^1.0.0"

acme-dev@^1.0.0:
  version "1.0.0"
  dependencies:
    acme-shared "^1.0.0"
    acme-devonly "^1.0.0"

acme-shared@^1.0.0:
  version "1.0.0"

acme-devonly@^1.0.0:
  version "1.0.0"
J
cat >pnpm/pnpm-lock.yaml <<'J'
lockfileVersion: '9.0'

importers:

  .:
    dependencies:
      acme-prod:
        specifier: ^1.0.0
        version: 1.0.0
    devDependencies:
      acme-dev:
        specifier: ^1.0.0
        version: 1.0.0

snapshots:

  acme-prod@1.0.0:
    dependencies:
      acme-shared: 1.0.0

  acme-dev@1.0.0:
    dependencies:
      acme-shared: 1.0.0
      acme-devonly: 1.0.0

  acme-shared@1.0.0: {}

  acme-devonly@1.0.0: {}
J
echo '{not json' >bad/package-lock.json
# yarn: prod root range "^2.0.0" is absent from the lock (resolutions); acme-prod is also under devDep acme-dev -> must stay prod
echo '{"name":"acme-app","dependencies":{"acme-prod":"^2.0.0"},"devDependencies":{"acme-dev":"^1.0.0"}}' >yres/package.json
printf '# yarn lockfile v1\n\nacme-prod@^1.0.0:\n  version "1.0.0"\n\nacme-dev@^1.0.0:\n  version "1.0.0"\n  dependencies:\n    acme-prod "^1.0.0"\n' >yres/yarn.lock
# pnpm: prod dep aliased to acme-prod@1.0.0, also reached via devDep acme-dev -> must stay prod
cat >palias/pnpm-lock.yaml <<'J'
lockfileVersion: '9.0'

importers:

  .:
    dependencies:
      acme-alias:
        specifier: npm:acme-prod@^1.0.0
        version: acme-prod@1.0.0
    devDependencies:
      acme-dev:
        specifier: ^1.0.0
        version: 1.0.0

snapshots:

  acme-prod@1.0.0: {}

  acme-dev@1.0.0:
    dependencies:
      acme-prod: 1.0.0
J
echo '{"name":"acme-app"}' >palias/package.json
# workspaces "packages/**": nested member depends on acme-prod, which the root lists as a devDependency -> must stay prod
mkdir -p ws/packages/a/b
echo '{"name":"acme-app","workspaces":["packages/**"],"devDependencies":{"acme-prod":"^1.0.0"}}' >ws/package.json
echo '{"name":"acme-b","dependencies":{"acme-prod":"^1.0.0"}}' >ws/packages/a/b/package.json
printf '# yarn lockfile v1\n\nacme-prod@^1.0.0:\n  version "1.0.0"\n' >ws/yarn.lock
# scoped dev-only package whose devDependency range is absent from the lock -> tagged (name fallback is scoped-safe)
echo '{"name":"acme-app","dependencies":{"acme-prod":"^1.0.0"},"devDependencies":{"@acme/devtool":"^2.0.0"}}' >scoped/package.json
printf '# yarn lockfile v1\n\nacme-prod@^1.0.0:\n  version "1.0.0"\n\n"@acme/devtool@^1.0.0":\n  version "1.0.0"\n' >scoped/yarn.lock
# yarn npm: alias: prod dep acme-alias -> npm:acme-dev, same real package also a devDependency -> acme-dev must stay prod
echo '{"name":"acme-app","dependencies":{"acme-alias":"npm:acme-dev@^1.0.0"},"devDependencies":{"acme-dev":"^1.0.0"}}' >yalias/package.json
printf '# yarn lockfile v1\n\n"acme-alias@npm:acme-dev@^1.0.0":\n  version "1.0.0"\n\nacme-dev@^1.0.0:\n  version "1.0.0"\n' >yalias/yarn.lock
# workspace outside the lockfile dir: its prod dep is unreadable -> fail closed (untagged), never dev
echo '{"name":"acme-app","workspaces":["../shared"],"devDependencies":{"acme-prod":"^1.0.0"}}' >wsout/package.json
echo '{"name":"acme-shared-ws","dependencies":{"acme-prod":"^1.0.0"}}' >shared/package.json
printf '# yarn lockfile v1\n\nacme-prod@^1.0.0:\n  version "1.0.0"\n' >wsout/yarn.lock
# no-range alias "acme-alias@npm:acme-dev": real package is acme-dev, also a devDependency -> stays prod
echo '{"name":"acme-app","dependencies":{"acme-alias":"npm:acme-dev"},"devDependencies":{"acme-dev":"^1.0.0"}}' >ynr/package.json
printf '# yarn lockfile v1\n\n"acme-alias@npm:acme-dev":\n  version "1.0.0"\n\nacme-dev@^1.0.0:\n  version "1.0.0"\n' >ynr/yarn.lock
# prod URL alias has no real name in yarn v1: fail closed (unknown), never a dev-only tag for the same-named devDependency
echo '{"name":"acme-app","dependencies":{"acme-alias":"https://example.com/acme-dev.tgz"},"devDependencies":{"acme-dev":"^1.0.0"}}' >yurl/package.json
printf '# yarn lockfile v1\n\n"acme-alias@https://example.com/acme-dev.tgz":\n  version "1.0.0"\n\nacme-dev@^1.0.0:\n  version "1.0.0"\n' >yurl/yarn.lock
g add . && g commit -q -m deps
: >"$T/notadir"; export PERUN_HEAVY_DIR="$T/notadir"
REVIEW_OSV=1 PATH="$T/bin:$PATH" bash "$RC" --base base 2>"$T/err" >"$T/out" || true
tags() { jq -r --arg f "$1" '[.[] | select(.file==$f and .tool=="osv-scanner" and (.message|endswith("(scope: dev)"))) | .message|capture("acme-(?<n>[a-z]+)@").n] | sort | join(",")' "$T/out"; }
rows() { jq -r --arg f "$1" '[.[] | select(.file==$f and .line==0 and .rule!="not-checked")] | length' "$T/out"; }
[ "$(tags npm/package-lock.json)" = dev ] && r=0 || r=1; chk $r "package-lock v3: only the dev:true-only package is tagged (shared prod, devOptional, unknown untagged)"
[ "$(tags yarn/yarn.lock)" = dev,devonly ] && r=0 || r=1; chk $r "yarn v1: dev-only walk tags acme-dev and acme-devonly; acme-shared (prod too) untagged"
[ "$(tags pnpm/pnpm-lock.yaml)" = dev,devonly ] && r=0 || r=1; chk $r "pnpm v9: importers/snapshots walk tags acme-dev and acme-devonly; acme-shared untagged"
[ "$(tags bad/package-lock.json)" = "" ] && [ "$(rows bad/package-lock.json)" = 5 ] && r=0 || r=1; chk $r "unparseable lockfile: no tag, all 5 rows kept"
[ "$(rows npm/package-lock.json)" = 6 ] && [ "$(rows yarn/yarn.lock)" = 5 ] && [ "$(rows pnpm/pnpm-lock.yaml)" = 5 ] && r=0 || r=1; chk $r "row counts unchanged by tagging (npm 5 osv + 1 trivy, yarn 5, pnpm 5)"
[ "$(jq -r '[.[] | select(.tool=="trivy" and .rule=="CVE-T")][0].message' "$T/out")" = "high: acme-dev@1.0.0: tt (scope: dev)" ] && r=0 || r=1; chk $r "trivy row tagged the same way, severity prefix unchanged"
[ "$(jq -r '[.[] | select(.file=="npm/package-lock.json" and .tool=="osv-scanner" and (.message|test("acme-dev@")))][0].message' "$T/out")" = "high: acme-dev@1.0.0: s (scope: dev)" ] && r=0 || r=1; chk $r "osv row message keeps severity and title, tag appended last"
[ "$(tags yres/yarn.lock)" = dev ] && r=0 || r=1; chk $r "yarn: prod root range missing from lock (resolutions) + same pkg under a devDep -> acme-prod untagged"
[ "$(tags palias/pnpm-lock.yaml)" = dev ] && r=0 || r=1; chk $r "pnpm: aliased prod dep also under a devDep -> acme-prod untagged"
[ "$(tags ws/yarn.lock)" = "" ] && r=0 || r=1; chk $r "workspaces packages/**: nested member prod dep also a root devDep -> untagged"
[ "$(jq -r '[.[] | select(.file=="scoped/yarn.lock" and (.message|test("^high: @acme/devtool@1.0.0: s \\(scope: dev\\)$")))] | length' "$T/out")" = 1 ] && [ "$(tags scoped/yarn.lock)" = "" ] && r=0 || r=1; chk $r "scoped dev-only package tagged, prod untagged"
[ "$(tags yalias/yarn.lock)" = "" ] && r=0 || r=1; chk $r "yarn npm: alias: prod alias of acme-dev + devDep acme-dev -> acme-dev untagged"
[ "$(tags wsout/yarn.lock)" = "" ] && r=0 || r=1; chk $r "workspace glob outside the lockfile dir: fail closed, nothing tagged dev"
[ "$(tags ynr/yarn.lock)" = "" ] && r=0 || r=1; chk $r "yarn: no-range prod alias npm:acme-dev + devDep acme-dev -> acme-dev untagged"
[ "$(tags yurl/yarn.lock)" = "" ] && r=0 || r=1; chk $r "yarn: prod URL alias -> unknown scope, nothing tagged dev"
SC="$T/sc"; mkdir -p "$SC"; printf '# yarn lockfile v1\n\n"acme-alias@npm:@acme/real":\n  version "1.0.0"\n\n"@acme/real@^1.0.0":\n  version "1.0.0"\n' >"$SC/yarn.lock"
echo '{"name":"acme-app","dependencies":{"acme-alias":"npm:@acme/real"},"devDependencies":{"@acme/real":"^1.0.0"}}' >"$SC/package.json"
python3 -I -c 'import sys,importlib.util as u;s=u.spec_from_file_location("d",sys.argv[1]);m=u.module_from_spec(s);s.loader.exec_module(m);p,d=m.scope_sets(sys.argv[2]);sys.exit(0 if "@acme/real@1.0.0" in p else 1)' "$ROOT/.claude/skills/deep-code-review/scripts/dep_scope.py" "$SC/yarn.lock" && r=0 || r=1; chk $r "yarn: scoped no-range alias npm:@acme/real resolves to the scoped real name (prod)"
PU="$T/pu"; mkdir -p "$PU/a" "$PU/b"; PYS='import sys,importlib.util as u;s=u.spec_from_file_location("d",sys.argv[1]);m=u.module_from_spec(s);s.loader.exec_module(m);r=m.scope_sets(sys.argv[2]);sys.exit(0 if '
cat >"$PU/a/pnpm-lock.yaml" <<'J'
lockfileVersion: '9.0'

importers:

  .:
    dependencies:
      acme-alias:
        specifier: https://example.com/acme-dev-1.0.0.tgz
        version: https://example.com/acme-dev-1.0.0.tgz
    devDependencies:
      acme-dev:
        specifier: ^1.0.0
        version: 1.0.0

snapshots:

  acme-dev@https://example.com/acme-dev-1.0.0.tgz: {}

  acme-dev@1.0.0: {}
J
python3 -I -c "$PYS"'"acme-dev@1.0.0" in r[0] else 1)' "$ROOT/.claude/skills/deep-code-review/scripts/dep_scope.py" "$PU/a/pnpm-lock.yaml" && r=0 || r=1; chk $r "pnpm: prod URL dep + devDep of the same package -> acme-dev@1.0.0 not dev-only"
printf "lockfileVersion: '9.0'\n\nimporters:\n\n  .:\n    dependencies:\n      acme-gone:\n        specifier: ^1.0.0\n        version: 1.0.0\n\nsnapshots:\n\n  acme-other@1.0.0: {}\n" >"$PU/b/pnpm-lock.yaml"
python3 -I -c "$PYS"'r is None else 1)' "$ROOT/.claude/skills/deep-code-review/scripts/dep_scope.py" "$PU/b/pnpm-lock.yaml" && r=0 || r=1; chk $r "pnpm: prod dep with no matching snapshot -> unknown (scope_sets None)"
mkdir -p "$PU/c" "$PU/d"
cat >"$PU/c/pnpm-lock.yaml" <<'J'
lockfileVersion: '9.0'

importers:

  .:
    dependencies:
      acme-fork:
        specifier: github:acme/acme-lib#abc123
        version: github.com/acme/acme-lib/abc123
    devDependencies:
      acme-lib:
        specifier: github:acme/acme-lib#abc123
        version: github.com/acme/acme-lib/abc123

snapshots:

  acme-lib@github.com/acme/acme-lib/abc123: {}

  acme-fork@1.0.0: {}
J
python3 -I -c "$PYS"'"acme-fork@1.0.0" not in r[0] and "acme-lib@github.com/acme/acme-lib/abc123" in r[0] else 1)' "$ROOT/.claude/skills/deep-code-review/scripts/dep_scope.py" "$PU/c/pnpm-lock.yaml" && r=0 || r=1; chk $r "pnpm: git-shorthand alias key matches by version part, never the same-name alias snapshot"
cat >"$PU/d/pnpm-lock.yaml" <<'J'
lockfileVersion: '9.0'

importers:

  .:
    dependencies:
      acme-alias:
        specifier: npm:acme-real@1.0.0
        version: 'acme-real@1.0.0'
    devDependencies:
      acme-real:
        specifier: ^1.0.0
        version: 1.0.0

snapshots:

  acme-real@1.0.0: {}
J
python3 -I -c "$PYS"'"acme-real@1.0.0" in r[0] else 1)' "$ROOT/.claude/skills/deep-code-review/scripts/dep_scope.py" "$PU/d/pnpm-lock.yaml" && r=0 || r=1; chk $r "pnpm: quoted importer alias version resolves to the real snapshot (prod)"
echo "Tests: $pass/$total"; [ "$pass" = "$total" ]
