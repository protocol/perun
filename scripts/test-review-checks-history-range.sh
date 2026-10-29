#!/usr/bin/env bash
# review_checks.sh --history scans the commits BASE..HEAD adds, never BASE...HEAD: the symmetric range also scans every
# BASE-only commit when the branch is behind BASE, so main's history raises findings against the PR. Stub gitleaks on PATH
# lists the commit subjects of the --log-opts range it is given, so the cases run offline in CI.
set -uo pipefail  # no -e: a failed grep must reach chk, which prints the FAIL line
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-hist.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin"
cat >"$T/bin/gitleaks" <<'STUB'
#!/usr/bin/env bash
rep=; opts=; a=("$@")
for i in "${!a[@]}"; do [ "${a[$i]}" = -r ] && rep=${a[$((i + 1))]}; [ "${a[$i]}" = --log-opts ] && opts=${a[$((i + 1))]}; done
echo '[]' >"$rep"
[ -z "$opts" ] || git log --format=%s "$opts" >>"$HIST_LOG"
STUB
printf '#!/bin/sh\nexit 1\n' >"$T/bin/semgrep"  # no real semgrep: it would reach for the network
chmod +x "$T/bin/gitleaks" "$T/bin/semgrep"; export PATH="$T/bin:$PATH" HIST_LOG="$T/hist"
mkdir "$T/r"; cd "$T/r"; g init -q -b main .
echo a >a.txt; g add -A; g commit -q -m base-commit
g checkout -q -b feat; echo b >b.txt; g add -A; g commit -q -m branch-only
g checkout -q main; echo c >c.txt; g add -A; g commit -q -m main-only; g checkout -q feat
scan() { : >"$HIST_LOG"; bash "$RC" --base main --history >/dev/null 2>&1 || true; }
scan
grep -qx branch-only "$HIST_LOG"; chk $? "behind BASE: the branch's own commit is scanned"
! grep -qx main-only "$HIST_LOG"; chk $? "behind BASE: a BASE-only commit is not scanned"
g merge -q --no-edit main
scan
grep -qx branch-only "$HIST_LOG"; chk $? "after merging BASE: the branch's own commit is scanned"
! grep -qxE 'main-only|base-commit' "$HIST_LOG"; chk $? "after merging BASE: BASE's history is not scanned"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
