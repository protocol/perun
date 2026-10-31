#!/usr/bin/env bash
# Tests for tenant_scope_check.py on a generated fixture: exact findings (recall + precision), exit 0, JSON summary, and a stub guard.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TS="$ROOT/.claude/skills/deep-code-review/scripts/tenant_scope_check.py"
W="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-tenant-scope.XXXXXX")"
trap '[ -n "$W" ] && rm -rf "$W"' EXIT
mkdir -p "$W/prisma" "$W/app/(dash)" "$W/app/api/notes" "$W/lib" "$W/empty"
cat >"$W/prisma/schema.prisma" <<'P'
model Workspace {
  id   String @id
  name String
}
model PendingAccess {
  id          String @id
  workspaceId String
  workspace   Workspace @relation(fields: [workspaceId], references: [id])
}
model Note {
  id   String @id
  wsId String
  ws   Workspace @relation(fields: [wsId], references: [id])
}
model Plan {
  id   String @id
  name String
}
P
cat >"$W/app/(dash)/actions.ts" <<'A'
"use server";
// db.pendingAccess.delete({ where: { id } }) -- comment, never flagged
export async function revoke(id: string, workspaceId: string) {
  await db.pendingAccess.delete({ where: { id } });
  await db.pendingAccess.update({ where: { id, workspaceId }, data: { n: 1 } });
  await db.pendingAccess.findFirst({ where: { id_workspaceId: { id, workspaceId } } });
  await db.pendingAccess.deleteMany({ where: { id: { in: ids }, AND: [{ workspaceId }] } });
  await db.pendingAccess.findUnique({ where: { id, workspace: { members: { some: {} } } } });
  await db.pendingAccess.findUnique({ where: filter });
  await db.pendingAccess.findUnique({ where: { ...filter, id } });
  // tenant-scope-ok: verified by the caller
  await db.pendingAccess.delete({ where: { id } });
  await db.plan.delete({ where: { id } });
  const s = "db.pendingAccess.delete({ where: { id } })";
  const c = await db.note.count({});
  return db.note.findMany({});
}
export async function more(id: string, workspaceId: string, x: any) {
  await db.pendingAccess.update({ where: { id, "workspaceId": workspaceId }, data: {} });
  await db.pendingAccess.update({ where: { id, ["workspaceId"]: workspaceId }, data: {} });
  await db.pendingAccess.update({ where: { id: x.workspaceId }, data: {} });
  await db.pendingAccess.findFirst({ where: { id, OR: [{ workspaceId }, { isPublic: true }] } });
  await db.pendingAccess.upsert({ where: { id }, create: {}, update: {} });
  await db.pendingAccess.findUniqueOrThrow({ where: { id } });
  await db.pendingAccess.findUnique({ where: { id, AND: { workspaceId } } });
}
A
cat >"$W/app/api/notes/route.ts" <<'A'
export async function GET() { return db.note.findFirst({ where: { id: 1 } }); }
A
# Out of scope: a non-server file and a test file hold the same bad call and must stay silent.
echo 'export const x = () => db.pendingAccess.delete({ where: { id } });' >"$W/lib/util.ts"
echo 'db.pendingAccess.delete({ where: { id } });' >"$W/app/(dash)/actions.test.ts"

pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
out=$(python3 -I "$TS" "$W" 2>"$W/stderr"); rc=$?
lines=$(grep -E '^[^{].*: (HIGH|MED): ' <<<"$out")
H='unscoped tenant access: db.pendingAccess.'
want="app/(dash)/actions.ts:4: HIGH: ${H}delete where has id but not workspaceId
app/(dash)/actions.ts:21: HIGH: ${H}update where has id but not workspaceId
app/(dash)/actions.ts:22: HIGH: ${H}findFirst where has id but not workspaceId
app/(dash)/actions.ts:23: HIGH: ${H}upsert where has id but not workspaceId
app/(dash)/actions.ts:24: HIGH: ${H}findUniqueOrThrow where has id but not workspaceId
app/api/notes/route.ts:1: MED: model missing tenant key: Note links to a tenant model but has none of workspaceId/orgId/tenantId/teamId; scope via a parent relation if present"
[ "$rc" -eq 0 ]; ok $? "exit 0 (report-only)"
[ "$lines" = "$want" ]; ok $? "exactly the 5 HIGH and 1 MED expected (recall + precision)"
grep -q 'unscoped tenant access' <<<"$lines" && ! grep -qE 'actions.ts:(5|6|7|8|9|10|11|13|14|15|16|19|20|25):' <<<"$lines"; ok $? "scoped, quoted/computed-key, AND, compound-key, relation, variable, spread, suppressed, global and string calls stay silent"
! grep -qE "actions.ts:(19|20|25):" <<<"$lines"; ok $? "quoted-key and computed-key scoped calls do not flag (#4)"
grep -q "actions.ts:21:" <<<"$lines" && grep -q "actions.ts:22:" <<<"$lines"; ok $? "id: x.workspaceId and OR-only scope flag (#5)"
grep -q "actions.ts:23: HIGH.*upsert" <<<"$lines" && grep -q "actions.ts:24: HIGH.*findUniqueOrThrow" <<<"$lines"; ok $? "upsert and findUniqueOrThrow id-only flag (#6)"
! grep -qE 'util.ts|actions.test.ts' <<<"$out"; ok $? "non-server and test files not scanned"
[ "$(grep -c 'model missing tenant key' <<<"$lines")" = 1 ] && ! grep -qE 'actions.ts:(15|16):.*MED' <<<"$lines"; ok $? "MED only on CALLS methods (count/findMany silent), once per file"
grep -qx 'heuristic; scanned 2 server files' "$W/stderr"; ok $? "stderr says heuristic + server file count"
j=$(tail -n1 <<<"$out"); python3 -I -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["high"]==5 and d["med"]==1 and d["server_files"]==2 and d["tenant_models"]==["pendingAccess"] and len(d["findings"])==6' "$j"; ok $? "JSON summary counts and tenant model list"
out=$(python3 -I "$TS" "$W/empty" 2>/dev/null); rc=$?
[ "$rc" -eq 0 ] && [ "$(wc -l <<<"$out" | tr -d ' ')" = 1 ]; ok $? "dir without a schema: exit 0, summary only"
python3 -I "$TS" "$W/nope" 2>/dev/null; [ $? -eq 2 ]; ok $? "bad DIR: exit 2"
# A backslash as the last character of a file, inside an open string, once raised IndexError in mask(): the scan must survive a truncated file.
mkdir -p "$W/bs/app/api/x"; cp -R "$W/prisma" "$W/bs/"; printf 'const s = "a\\' >"$W/bs/app/api/x/route.ts"
python3 -I "$TS" "$W/bs" >/dev/null 2>"$W/err0"; rc=$?
[ "$rc" -eq 0 ] && ! grep -q Traceback "$W/err0" && grep -qx 'heuristic; scanned 1 server files' "$W/err0"; ok $? "a backslash ending the file inside an open string: scanned, no crash"
# review_checks.sh --full: rows for the HIGH/MEDs when a *.prisma is tracked, a SKIPPED line when none is.
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
G="$W/git"; mkdir -p "$G"; cp -R "$W/prisma" "$W/app" "$G/"; git -C "$G" init -q
git -C "$G" add -A; git -C "$G" -c user.email=a@example.com -c user.name=Acme commit -qm fixture
out=$(PATH=/usr/bin:/bin bash "$RC" --full --repo "$G" 2>"$W/err"); n=$(grep -c '"tool": "tenant-scope"' <<<"$out")
[ "$n" = 6 ] && grep -q '"rule": "unscoped-tenant-access"' <<<"$out" && grep -q "tenant-scope: heuristic; scanned 2 server files" "$W/err"; ok $? "review_checks --full emits 6 tenant-scope rows (5 HIGH, 1 MED) and the scanned-files note"
G2="$W/git2"; mkdir -p "$G2"; echo 'export const a = 1;' >"$G2/a.ts"; git -C "$G2" init -q
git -C "$G2" add -A; git -C "$G2" -c user.email=a@example.com -c user.name=Acme commit -qm fixture
PATH=/usr/bin:/bin bash "$RC" --full --repo "$G2" >/dev/null 2>"$W/err2"; grep -q 'tenant-scope (SKIPPED: no \*.prisma)' "$W/err2"; ok $? "review_checks --full without a *.prisma reports SKIPPED"
echo "Tests: $pass/$((pass + fail))"
[ "$fail" -eq 0 ]
