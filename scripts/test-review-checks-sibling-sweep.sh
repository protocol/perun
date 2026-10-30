#!/usr/bin/env bash
# Tests for sibling_sweep.py and review_checks.sh's built-in sibling-sweep step. A fix changes the arguments of calls to checkQuota,
# mintToken (empty to one argument), sendAlert (a line inserted in a multi-line call) and notify (Python) in one route and leaves the
# same calls in sibling routes: those unchanged non-test call sites are the leads, ranked first when their arguments equal the old
# form. Not leads: the definitions, a test file, a call already in the new form, a same-named call in another language, calls to a
# name with more than 25 call sites (one not-checked row names them: the hub keeps rows and drops the script's stderr summary), and the router call whose callback body (not its own arguments) was edited. More than 5 leads for one name or 30 in all
# are cut, with one not-checked row counting the rest. A call far into a long line is still a lead and a long comment line is still no call. A last repo covers test
# paths by name only (tests.py, test.ts, *.mock.ts, __fixtures__/), a receiver named like a keyword (proc.wait(), impl.run(): calls, not definitions) and git colour codes
# (color.ui=always). The sweep reads commits, not the working tree. In review_checks.sh it runs in base mode only
# (not under --full), is listed under "analyzers ran", and a missing script gives one not-checked row. Hermetic: temp git repo,
# pruned PATH (no awk, no linters), no host git config or ~/.local/bin tools, fictional code.
set -euo pipefail
export DCR_USER_BIN='' GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1  # the host's provisioned tools and git config (colour, signing, hooks) must not change what is asserted
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
SS="$ROOT/.claude/skills/deep-code-review/scripts/sibling_sweep.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-sibsweep.XXXXXX"); trap 'rm -rf "$T"' EXIT
fail=0
ok() { printf 'ok   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }
G() { git -c user.email=t@example.com -c user.name=t "$@"; }

mkdir "$T/bin" "$T/nosweep" "$T/repo" "$T/cap" "$T/long" "$T/edge"
for c in git python3 bash sed grep head tail mktemp rm cat dirname perl env tr wc sleep timeout; do ln -s "$(command -v "$c")" "$T/bin/" 2>/dev/null || true; done
cp "$RC" "$T/nosweep/review_checks.sh"  # no sibling_sweep.py beside it
export PERUN_HEAVY_DIR="$T/heavy"

cd "$T/repo"
G init -q . && G commit -q --allow-empty -m empty
leak=$(git config --list --show-origin | cut -f1 | grep '^file:' | grep -vx 'file:\.git/config' || true)  # config files other than the repo's own; origins only, a value could be the host user's
[ -z "${DCR_USER_BIN-x}" ] && [ -z "$leak" ] && ok "hermetic: no host tool dir, no global or system git config" || bad "host environment leaks in: DCR_USER_BIN=${DCR_USER_BIN-unset}, config from ${leak:-none}"
mkdir -p src/routes src/__tests__ tests svc tools
cat >src/limits.ts <<'EOF'
export function checkQuota(key: string): boolean {
  return key.length > 0;
}
export function mintToken(): string {
  return "t";
}
export function sendAlert(user: string, level: number): void {}
EOF
cat >src/routes/a.ts <<'EOF'
import { checkQuota, mintToken, sendAlert } from "../limits";

export function routeA(user: string) {
  if (!checkQuota(user)) return null;
  const t = mintToken();
  sendAlert(
    user,
    1
  );
  return t;
}
EOF
cat >src/routes/b.ts <<'EOF'
import { checkQuota, sendAlert } from "../limits";

export function routeB(user: string) {
  if (!checkQuota(user)) return null;
  sendAlert(user, 1);
  return "b";
}
EOF
cat >src/routes/c.ts <<'EOF'
import { checkQuota, mintToken } from "../limits";

export function routeC(id: string) {
  if (!checkQuota(`other:${id}`)) return null;
  return mintToken();
}
EOF
cat >src/routes/d.ts <<'EOF'
import { checkQuota } from "../limits";

export function routeD(user: string) {
  return checkQuota(`quota:${user}`);
}
EOF
cat >src/routes/e.ts <<'EOF'
router.get("/e1", async (req) => {
  doWork(1);
});
router.get("/e2", async (req) => {
  doWork(1);
});
EOF
printf 'expect(checkQuota(user)).toBe(true);\n' >tests/limits.test.ts
printf 'expect(checkQuota(user)).toBe(true);\n' >src/__tests__/limits.ts
printf 'checkQuota(user)\n' >tools/report.py
cat >svc/core.py <<'EOF'
def notify(user, msg):
    return msg
EOF
printf 'def run_a(user):\n    return notify(user, "x")\n' >svc/a.py
printf 'def run_b(user):\n    return notify(user, "x")\n' >svc/b.py
{ echo 'import { audit } from "./audit";'; for i in $(seq 1 30); do echo "audit($i, \"x\");"; done; } >src/many.ts
G add . && G commit -q -m base
git branch base

# the fix: every changed call is in routes a, e1, many (line 8) and svc/a.py; their siblings are left alone
cat >src/routes/a.ts <<'EOF'
import { checkQuota, mintToken, sendAlert } from "../limits";

export function routeA(user: string) {
  if (!checkQuota(`quota:${user}`)) return null;
  const t = mintToken(user);
  sendAlert(
    user,
    "mail",
    1
  );
  return t;
}
EOF
cat >src/routes/e.ts <<'EOF'
router.get("/e1", async (req) => {
  doWork(2);
});
router.get("/e2", async (req) => {
  doWork(1);
});
EOF
sed -i.bak '8s/"x"/"y"/' src/many.ts && rm src/many.ts.bak
printf 'def run_a(user):\n    return notify(user, "x", urgent=True)\n' >svc/a.py
G add . && G commit -q -m fix
rows() { cut -f1,2,3 "$1" | tr '\t' ':'; }

python3 -I "$SS" --repo . --base base --head HEAD >"$T/out.tsv" 2>"$T/err" || true
want="src/routes/b.ts:4:unchanged-sibling-call
src/routes/e.ts:5:unchanged-sibling-call
src/routes/c.ts:5:unchanged-sibling-call
svc/b.py:2:unchanged-sibling-call
src/routes/b.ts:5:unchanged-sibling-call
src/routes/c.ts:4:unchanged-sibling-call
.:0:not-checked"
[ "$(rows "$T/out.tsv")" = "$want" ] && ok "leads: sibling call sites, old-form arguments first, then by name, then the not-checked row" || bad "lead rows: $(rows "$T/out.tsv")"
grep -q '^src/routes/b.ts.4.unchanged-sibling-call.lead: checkQuota(user) is unchanged, but this diff changed the arguments of checkQuota at src/routes/a.ts:4 (user -> `quota:${user}`); same arguments as the old form$' "$T/out.tsv" \
  && ok "message names the call, the changed site and the old and new arguments" || bad "message shape"
grep -q 'checkQuota(`other:${id}`) is unchanged' "$T/out.tsv" && ! grep 'other:' "$T/out.tsv" | grep -q 'same arguments as the old form' && ok "different arguments: a lead, without the old-form tag" || bad "tier-1 row"
[ "$(grep unchanged-sibling-call "$T/out.tsv" | cut -f1 | sort -u | tr '\n' ' ')" = "src/routes/b.ts src/routes/c.ts src/routes/e.ts svc/b.py " ] && ! grep -q 'arguments of get ' "$T/out.tsv" \
  && ok "test paths, definitions, a call already in the new form, another language, a name over 25 sites and a callback edit are not leads" || bad "excluded sites listed: $(grep unchanged-sibling-call "$T/out.tsv" | cut -f1 | sort -u | tr '\n' ' ')"
grep -Fxq $'.\t0\tnot-checked\tsibling sweep partial: not swept, over 25 call sites: audit' "$T/out.tsv" \
  && ok "a name over 25 call sites is a not-checked row, not only a stderr note" || bad "over-cap row: $(grep not-checked "$T/out.tsv" || echo none)"
grep -q 'not swept, over 25 call sites: audit' "$T/err" && grep -q '6 lead(s), not findings' "$T/err" && ok "stderr summary: 6 leads, not findings; the over-common name is named" || bad "summary: $(cat "$T/err")"
grep -q 'sendAlert(user, 1) is unchanged.*(user, 1 -> user, "mail", 1)' "$T/out.tsv" && ok "a line inserted into a multi-line call counts as an argument change" || bad "multi-line insertion"
grep -q 'mintToken() is unchanged.*( -> user)' "$T/out.tsv" && ok "empty old arguments are an old form too" || bad "empty-argument form"

# reads commits, not the working tree: with base checked out (the fix absent from the files), sweep the fix commit
git branch fix && git checkout -q base
python3 -I "$SS" --repo . --base base --head fix >"$T/out2.tsv" 2>/dev/null || true
[ "$(rows "$T/out2.tsv")" = "$want" ] && [ -z "$(git status --porcelain)" ] && ok "sweeping a commit that is not checked out gives the same leads and touches nothing" || bad "commit-only sweep"
git checkout -q fix

python3 -I "$SS" --repo . --base nosuchref >/dev/null 2>"$T/err3" && bad "bad ref should exit 2" || { [ "$?" = 2 ] && grep -q 'unresolvable ref' "$T/err3" && ok "unresolvable ref exits 2" || bad "bad ref exit"; }
python3 -I "$SS" --repo . --base=-x >/dev/null 2>"$T/err4" && bad "ref starting with - accepted" || { [ "$?" = 2 ] && grep -q "must not start with" "$T/err4" && ok "ref starting with - refused (exit 2)" || bad "dash ref: $(cat "$T/err4")"; }

# review_checks.sh --base: leads are sibling-sweep rows, listed under analyzers ran
PATH="$T/bin" bash "$RC" --base base 2>"$T/rerr" >"$T/rout" || true
jq -e '[.[] | select(.tool=="sibling-sweep" and .rule!="not-checked")] | length == 6 and all(.[]; .rule=="unchanged-sibling-call" and (.text|startswith("unchanged-sibling-call: lead: ")) and .line>0 and (has("hint")|not))' "$T/rout" >/dev/null \
  && ok "review_checks.sh: 6 sibling-sweep lead rows with the usual row shape" || bad "rows: $(jq -c '[.[]|select(.tool=="sibling-sweep")|.file]' "$T/rout")"
jq -e '[.[] | select(.tool=="sibling-sweep" and .rule=="not-checked")] | length == 1 and (.[0].message|contains("not swept, over 25 call sites: audit"))' "$T/rout" >/dev/null \
  && ok "review_checks.sh keeps the over-cap name as one not-checked row (it drops the stderr summary)" || bad "over-cap row: $(jq -c '[.[]|select(.tool=="sibling-sweep" and .rule=="not-checked")|.message]' "$T/rout")"
grep -Eq 'analyzers ran:.* sibling-sweep' "$T/rerr" && ok "listed under analyzers ran" || bad "analyzers ran"
! grep -q 'NOT RUN: .*sibling-sweep' "$T/rerr" && ! grep -q '^sibling_sweep:' "$T/rout" && ok "no NOT RUN entry; the script's stderr summary is not a row" || bad "not-run or summary row"
PATH="$T/bin" bash "$RC" --base base --full 2>"$T/rerr1" >"$T/rout1" || true
jq -e 'all(.[]; .tool!="sibling-sweep")' "$T/rout1" >/dev/null && ! grep -Eq 'analyzers ran:.* sibling-sweep' "$T/rerr1" && ok "--full does not run it (no diff)" || bad "--full ran the sweep"
PATH="$T/bin" bash "$T/nosweep/review_checks.sh" --base base 2>"$T/rerr2" >"$T/rout2" || true
jq -e '[.[] | select(.tool=="sibling-sweep")] | length == 1 and .[0].rule=="not-checked" and (.[0].message|contains("sibling_sweep.py missing"))' "$T/rout2" >/dev/null \
  && grep -q 'not run: sibling-sweep' "$T/rerr2" && ! grep -Eq 'analyzers ran:.* sibling-sweep' "$T/rerr2" && ok "script missing gives one not-checked row, not listed as ran" || bad "missing-script row"

# caps: eight changed names with 6 unchanged sites each = 48 leads; 5 per name (40), 30 in all, and one not-checked row counting the other 18
cd "$T/cap"
G init -q . && G commit -q --allow-empty -m empty
for n in A B C D E F G H; do for i in 1 2 3 4 5 6; do echo "emit$n($i);"; done; done >bulk.ts
for n in A B C D E F G H; do echo "emit$n(0);"; done >one.ts
G add . && G commit -q -m base && git branch base
for n in A B C D E F G H; do echo "emit$n(0, true);"; done >one.ts
G add . && G commit -q -m fix
python3 -I "$SS" --repo . --base base >"$T/cap.tsv" 2>/dev/null || true
[ "$(grep -c unchanged-sibling-call "$T/cap.tsv")" = 30 ] && [ "$(grep unchanged-sibling-call "$T/cap.tsv" | grep -c 'emitA(')" = 5 ] && [ "$(grep -c not-checked "$T/cap.tsv")" = 1 ] \
  && grep -Fxq $'.\t0\tnot-checked\tsibling sweep partial: 18 more sibling lead(s) not listed (cap 5 per function, 30 in all)' "$T/cap.tsv" \
  && ok "caps: 5 rows per name, 30 in all, one not-checked row counting the rest" || bad "caps: $(cut -f1-3 "$T/cap.tsv" | sort | uniq -c | head -5)"

# long lines: only the 300 characters before a call decide whether it is a definition (a one-line bundle must not be quadratic), so a call
# far into a long line is still a lead, and a call inside a long comment line is still no call
cd "$T/long"
G init -q . && G commit -q --allow-empty -m empty
pad=$(python3 -c 'print("x" * 400)')
printf 'checkQuota(user);\n' >route.ts
printf 'const pad = "%s"; checkQuota(a);\n// %s checkQuota(b)\n' "$pad" "$pad" >long.ts
G add . && G commit -q -m base && git branch base
printf 'checkQuota(user, 1);\n' >route.ts
G add . && G commit -q -m fix
python3 -I "$SS" --repo . --base base >"$T/long.tsv" 2>/dev/null || true
[ "$(rows "$T/long.tsv")" = "long.ts:1:unchanged-sibling-call" ] && ok "long lines: a call 400 characters into its line is a lead, a call in a long comment is not" || bad "long lines: $(rows "$T/long.tsv")"

# edge cases. checkQuota and mintToken (called through `impl.`) change in src/a.ts, notify in svc/a.py. Their one non-test sibling each is a lead:
# `proc.checkQuota(user)` (a receiver named like a keyword is a call, not a definition), `mintToken()` and svc/b.py. app/tests.py, src/test.ts, src/a.mock.ts
# and src/__fixtures__/q.ts hold the same calls and are test paths. Then git is told to colour its output, which must change nothing.
cd "$T/edge"
G init -q . && G commit -q --allow-empty -m empty
mkdir -p src/__fixtures__ svc app
printf 'checkQuota(user);\nimpl.mintToken();\n' >src/a.ts
printf 'proc.checkQuota(user);\nmintToken();\n' >src/b.ts
for f in src/test.ts src/a.mock.ts src/__fixtures__/q.ts; do printf 'checkQuota(user);\nmintToken();\n' >"$f"; done
for f in svc/a.py svc/b.py app/tests.py; do printf 'notify(user, "x")\n' >"$f"; done
G add . && G commit -q -m base && git branch base
printf 'checkQuota(user, 1);\nimpl.mintToken(user);\n' >src/a.ts
printf 'notify(user, "x", urgent=True)\n' >svc/a.py
G add . && G commit -q -m fix
python3 -I "$SS" --repo . --base base >"$T/edge.tsv" 2>/dev/null || true
! cut -f1 "$T/edge.tsv" | grep -Eq '(^|/)(tests\.py|test\.ts|a\.mock\.ts)$|__fixtures__' && grep -q '^svc/b.py' "$T/edge.tsv" \
  && ok "test paths by name only (tests.py, test.ts, a.mock.ts) and __fixtures__/ are not swept" || bad "test-named paths listed: $(cut -f1 "$T/edge.tsv" | sort -u | tr '\n' ' ')"
grep -q '^src/b.ts.1.unchanged-sibling-call.lead: checkQuota(user) is unchanged' "$T/edge.tsv" && grep -q '^src/b.ts.2.unchanged-sibling-call.lead: mintToken() is unchanged.* of mintToken at src/a.ts:2 ' "$T/edge.tsv" \
  && ok "a receiver named like a keyword (proc., impl.) is a call: a changed one is seen, a sibling is a lead" || bad "keyword receiver: $(rows "$T/edge.tsv" | tr '\n' ' ')"
edge="src/b.ts:1:unchanged-sibling-call
src/b.ts:2:unchanged-sibling-call
svc/b.py:1:unchanged-sibling-call"
git config color.ui always
python3 -I "$SS" --repo . --base base >"$T/edge2.tsv" 2>/dev/null || true
[ "$(rows "$T/edge2.tsv")" = "$edge" ] && ok "color.ui=always changes nothing: the same 3 leads, not 0" || bad "colour: $(rows "$T/edge2.tsv" | tr '\n' ' ')"

[ "$fail" = 0 ]
