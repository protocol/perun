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
RG=$(command -v gitleaks || true)  # real gitleaks, looked up before the stub shadows it
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
# --- --full: bounded history pass (bar items 1-4). Real gitleaks when installed; the token is built at run time, never printed.
if [ -n "$RG" ]; then
  ln -sf "$RG" "$T/bin/gitleaks"
  TOK="ghp_$(printf 'aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3z5A' | head -c 36)"
  H=$T/h; mkdir "$H"; cd "$H"; g init -q -b main .
  printf 'token=%s\n' "$TOK" >README.md; g add -A; g commit -q -m add; echo 'token=PLACEHOLDER' >README.md; g commit -q -am rm
  rows() { grep -c '"tool": *"gitleaks-history"' "$1" || true; }
  run() { local o=$1; shift; bash "$RC" --repo "$H" "$@" >"$T/$o.out" 2>"$T/$o.err"; echo $? >"$T/$o.rc"; }
  run full --full
  [ "$(rows "$T/full.out")" -ge 1 ]; chk $? "--full: removed-from-tree secret is a gitleaks-history row"
  ! grep -rqF "$TOK" "$T"/full.out "$T"/full.err; chk $? "--full: token never in stdout/stderr"
  REVIEW_HISTORY_MAX=0 run off --full
  [ "$(rows "$T/off.out")" = 0 ] && grep -rq 'history not scanned' "$T/off.out" "$T/off.err"; chk $? "REVIEW_HISTORY_MAX=0: no rows, history named not scanned"
  REVIEW_HISTORY_MAX=00 run off0 --full
  [ "$(rows "$T/off0.out")" = 0 ] && grep -rq 'history not scanned' "$T/off0.out" "$T/off0.err"; chk $? "REVIEW_HISTORY_MAX=00 is read as 0, not a silent empty scan"
  REVIEW_HISTORY_MAX=1 run one --full
  [ "$(rows "$T/one.out")" = 0 ]; chk $? "REVIEW_HISTORY_MAX=1: the secret commit 2 back is outside the bound"
  [ "$(cat "$T/full.rc")" = 0 ] && ! grep -q 'not run: gitleaks' "$T/full.err"; chk $? "fewer commits than N: exit 0, no error row"
  git clone -q --depth 1 "file://$H" "$T/sh"; H=$T/sh; run shal --full
  [ "$(cat "$T/shal.rc")" = 0 ] && ! grep -q 'not run: gitleaks' "$T/shal.err"; chk $? "shallow clone: exit 0, no error row"
  H=$T/h; run fh --full-history --base main; run hs --history --base HEAD~1
  [ "$(rows "$T/fh.out")" -ge 1 ]; chk $? "--full-history still scans the whole history"
  [ "$(rows "$T/hs.out")" = 0 ]; chk $? "--history BASE..HEAD range unchanged (secret commit is before BASE)"
  # diff mode takes no history pass: rows carry no gitleaks-history tool
  run diff --base HEAD~1; [ "$(rows "$T/diff.out")" = 0 ]; chk $? "diff mode: no gitleaks-history rows"
else echo "SKIP  --full history asserts: gitleaks not installed"
fi
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
