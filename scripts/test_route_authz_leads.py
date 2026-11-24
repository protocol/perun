"""route_auth_map.py --privileged MASS, MASS-CHECKED, IDMIX and CHILD rows (authz_leads): an authenticated NestJS, Express or Next.js write whose client body reaches an ORM write
with a privileged field and no strip or pick (MASS, CWE-915), whose access check takes the path id while the write's where takes a body id (IDMIX), or whose
child row takes its parent key from the body with no tie to the path parent (CHILD, CWE-639). Each class has a positive fixture and a fixed negative, so
removing the fix turns the negative back into the positive. Fixtures are fictional (widgets, projects, teams, Acme)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/route_auth_map.py"
CLASSES = ("MASS", "MASS-CHECKED", "MASS-ADMIN", "IDMIX", "CHILD")


def leads(files):
    """{(KIND, METHOD)} of the authz rows route_auth_map.py --privileged prints for files {relative path: text}."""
    with tempfile.TemporaryDirectory() as d:
        for rel, text in files.items():
            (Path(d) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(d) / rel).write_text(text)
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--privileged", d], capture_output=True, text=True, check=True)
    rows = [ln.split(":", 2)[2].split() for ln in r.stdout.splitlines()]
    return {(w[0][:-1], w[1]) for w in rows if w[0][:-1] in CLASSES}


def raw(rel, text):
    """The --privileged stdout for one file {rel: text}."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / rel).parent.mkdir(parents=True, exist_ok=True)
        (Path(d) / rel).write_text(text)
        return subprocess.run([sys.executable, "-I", str(SCRIPT), "--privileged", d], capture_output=True, text=True, check=True).stdout


def nest(controller, service, dto=""):
    return leads({"src/w/w.controller.ts": controller, "src/w/w.service.ts": service, "src/w/w.dto.ts": dto})


HEAD = "import { Body, Controller, Param, Patch, Post, Put, Req, UseGuards } from '@nestjs/common';\n"


def controller(member, svc="WidgetsService"):
    return HEAD + """
@Controller('widgets')
export class WidgetsController {
  constructor(private readonly widgets: %s) {}

%s
}
""" % (svc, member)


def service(body):
    return "@Injectable()\nexport class WidgetsService {\n  constructor(private readonly prisma: PrismaService) {}\n\n%s\n}\n" % body


DTO = "export class UpdateWidgetDto {\n  name: string;\n  role?: string;\n  ownerUid?: string;\n}\n"
MASS_C = controller("""  @Patch(':uid')
  @UseGuards(AcmeGuard)
  update(@Param('uid') uid: string, @Body() dto: UpdateWidgetDto, @Req() req) {
    return this.widgets.update(uid, dto, req.user);
  }""")


class Mass(unittest.TestCase):
    def test_spread_of_dto_with_role_is_mass(self):
        s = service("  update(uid, dto, user) {\n    return this.prisma.widget.update({ where: { uid }, data: { ...dto } });\n  }")
        self.assertEqual(nest(MASS_C, s, DTO), {("MASS", "PATCH")})

    def test_dto_passed_as_data_is_mass(self):
        s = service("  update(uid, dto, user) {\n    return this.prisma.widget.update({ where: { uid }, data: dto });\n  }")
        self.assertEqual(nest(MASS_C, s, DTO), {("MASS", "PATCH")})

    def test_destructured_rest_without_the_field_is_fixed(self):
        s = service("  update(uid, dto, user) {\n    const { role, ownerUid, ...rest } = dto;\n    return this.prisma.widget.update({ where: { uid }, data: { ...rest } });\n  }")
        self.assertEqual(nest(MASS_C, s, DTO), set())
        s = service("  update(uid, dto, user) {\n    const { name, ...rest } = dto;\n    return this.prisma.widget.update({ where: { uid }, data: { ...rest } });\n  }")
        self.assertEqual(nest(MASS_C, s, DTO), {("MASS", "PATCH")})

    def test_delete_of_the_field_is_fixed(self):
        s = service("  update(uid, dto, user) {\n    delete dto.role;\n    delete dto.ownerUid;\n    return this.prisma.widget.update({ where: { uid }, data: { ...dto } });\n  }")
        self.assertEqual(nest(MASS_C, s, DTO), set())

    def test_dto_without_a_privileged_field_is_silent(self):
        s = service("  update(uid, dto, user) {\n    return this.prisma.widget.update({ where: { uid }, data: { ...dto } });\n  }")
        self.assertEqual(nest(MASS_C, s, "export class UpdateWidgetDto {\n  name: string;\n}\n"), set())

    def test_picked_fields_are_fixed(self):
        s = service("  update(uid, dto, user) {\n    return this.prisma.widget.update({ where: { uid }, data: { name: dto.name } });\n  }")
        self.assertEqual(nest(MASS_C, s, DTO), set())

    def test_allowlist_naming_the_field_is_mass_and_a_forbidden_check_demotes_it(self):
        c = controller("""  @Put(':uid')
  @UseGuards(AcmeGuard)
  update(@Param('uid') uid: string, @Body() body, @Req() req) {
    return this.widgets.update(uid, body, req.user);
  }""")
        s = service("  update(uid, body, user) {\n    const data: any = {};\n    copyObj(body, data, ['name', 'isVerified']);\n    return this.prisma.widget.update({ where: { uid }, data });\n  }")
        self.assertEqual(nest(c, s), {("MASS", "PUT")})
        c2 = c.replace("    return this.widgets", "    if (body.isVerified !== undefined && !req.user.isAdmin) throw new ForbiddenException();\n    return this.widgets")
        self.assertEqual(nest(c2, s), {("MASS-CHECKED", "PUT")})

    def test_isempty_gate_on_a_boolean_field_never_fires_so_stays_mass(self):
        c = controller("""  @Put(':uid')
  @UseGuards(AcmeGuard)
  update(@Param('uid') uid: string, @Body() body, @Req() req) {
    if (!isEmpty(body.isVerified) && !req.user.isAdmin) throw new ForbiddenException();
    return this.widgets.update(uid, body, req.user);
  }""")
        s = service("  update(uid, body, user) {\n    const data: any = {};\n    copyObj(body, data, ['name', 'isVerified']);\n    return this.prisma.widget.update({ where: { uid }, data });\n  }")
        self.assertEqual(nest(c, s), {("MASS", "PUT")})
        c2 = c.replace("!isEmpty(body.isVerified)", "body.isVerified !== undefined")
        self.assertEqual(nest(c2, s), {("MASS-CHECKED", "PUT")})
        # neutral shape: same isEmpty call on a non-privileged field is irrelevant to the lead
        c3 = c.replace("!isEmpty(body.isVerified)", "!isEmpty(body.name)")
        self.assertEqual(nest(c3, s), {("MASS", "PUT")})

    def test_dead_isempty_gate_with_live_looking_second_operand_stays_mass(self):
        c = controller("""  @Put(':uid')
  @UseGuards(AcmeGuard)
  update(@Param('uid') uid: string, @Body() body, @Req() req) {
    if (!isEmpty(dto.isAdmin) && !req.user.isAdmin) throw new ForbiddenException();
    return this.widgets.update(uid, body, req.user);
  }""")
        s = service("  update(uid, body, user) {\n    const data: any = {};\n    copyObj(body, data, ['name', 'isAdmin']);\n    return this.prisma.widget.update({ where: { uid }, data });\n  }")
        self.assertEqual(nest(c, s), {("MASS", "PUT")})
        c2 = c.replace("isAdmin", "isOrgAdmin")
        s2 = s.replace("isAdmin", "isOrgAdmin")
        self.assertEqual(nest(c2, s2), {("MASS", "PUT")})

    def test_dead_gate_after_unrelated_if_block_stays_mass(self):
        c = controller("""  @Put(':uid')
  @UseGuards(AcmeGuard)
  update(@Param('uid') uid: string, @Body() body, @Req() req) {
    if (!uid) { this.log(uid); }
    if (!isEmpty(dto.isVerified) && !requestor.isAdmin) throw new ForbiddenException();
    return this.widgets.update(uid, body, req.user);
  }""")
        s = service("  update(uid, body, user) {\n    const data: any = {};\n    copyObj(body, data, ['name', 'isVerified']);\n    return this.prisma.widget.update({ where: { uid }, data });\n  }")
        self.assertEqual(nest(c, s), {("MASS", "PUT")})

    def test_unrelated_pick_does_not_hide_mass(self):
        s = service("  update(uid, dto, user) {\n    const page = pick(this.query, ['page']);\n    return this.prisma.widget.update({ where: { uid }, data: { ...dto } });\n  }")
        self.assertEqual(nest(MASS_C, s, DTO), {("MASS", "PATCH")})
        s = service("  update(uid, dto, user) {\n    const data = pick(dto, ['name']);\n    return this.prisma.widget.update({ where: { uid }, data: { ...data } });\n  }")
        self.assertEqual(nest(MASS_C, s, DTO), set())  # pick of the body itself still counts as a strip
        s = service("  update(uid, dto, user) {\n    delete this.cache.role;\n    return this.prisma.widget.update({ where: { uid }, data: { ...dto } });\n  }")
        self.assertEqual(nest(MASS_C, s, DTO), {("MASS", "PATCH")})

    def test_forbidden_outside_the_if_body_is_not_a_check(self):
        c = controller("""  @Put(':uid')
  @UseGuards(AcmeGuard)
  update(@Param('uid') uid: string, @Body() body, @Req() req) {
    if (body.isVerified) { this.log(uid); }
    this.ready(uid) || this.deny(new ForbiddenException());
    return this.widgets.update(uid, body, req.user);
  }""")
        s = service("  update(uid, body, user) {\n    const data: any = {};\n    copyObj(body, data, ['name', 'isVerified']);\n    return this.prisma.widget.update({ where: { uid }, data });\n  }")
        self.assertEqual(nest(c, s), {("MASS", "PUT")})
        c2 = c.replace("{ this.log(uid); }", "{ throw new ForbiddenException(); }")
        self.assertEqual(nest(c2, s), {("MASS-CHECKED", "PUT")})

    def test_public_route_is_not_judged_here(self):
        c = MASS_C.replace("  @UseGuards(AcmeGuard)\n", "  @Public()\n")
        s = service("  update(uid, dto, user) {\n    return this.prisma.widget.update({ where: { uid }, data: { ...dto } });\n  }")
        self.assertEqual(nest(c, s, DTO), set())


ID_C = controller("""  @Patch(':uid/items')
  @UseGuards(AcmeGuard)
  edit(@Param('uid') projectUid: string, @Body() body, @Req() req) {
    return this.widgets.editItem(projectUid, req.user, body);
  }""")


class IdMix(unittest.TestCase):
    SVC = "  async editItem(projectUid, user, data) {\n    await this.assertCanEdit(user, projectUid);\n    return this.prisma.item.update({ where: %s, data: { name: data.name } });\n  }\n  async assertCanEdit(user, projectUid) {}"

    def test_where_on_body_id_after_check_on_path_id_is_idmix(self):
        self.assertEqual(nest(ID_C, service(self.SVC % "{ uid: data.uid }")), {("IDMIX", "PATCH")})

    def test_where_scoped_to_the_path_parent_is_fixed(self):
        self.assertEqual(nest(ID_C, service(self.SVC % "{ uid: data.uid, projectUid }")), set())

    def test_where_on_the_path_id_is_fixed(self):
        self.assertEqual(nest(ID_C, service(self.SVC % "{ uid: projectUid }")), set())

    def test_no_access_check_is_not_idmix(self):
        s = service(self.SVC.replace("await this.assertCanEdit(user, projectUid);", "") % "{ uid: data.uid }")
        self.assertEqual(nest(ID_C, s), set())


CH_C = controller("""  @Post(':uid/members')
  @UseGuards(AcmeGuard)
  add(@Param('uid') teamUid: string, @Body() body, @Req() req) {
    return this.widgets.addMember(teamUid, body, req.user);
  }""")


class Child(unittest.TestCase):
    SVC = "  async addMember(teamUid, body, user) {\n    await this.assertTeamLead(user, teamUid);\n%s    return this.prisma.teamMember.create({ data: { memberUid: body.memberUid, teamUid: %s } });\n  }\n  async assertTeamLead(user, teamUid) {}"

    def test_parent_key_from_body_is_child(self):
        self.assertEqual(nest(CH_C, service(self.SVC % ("", "body.teamUid"))), {("CHILD", "POST")})

    def test_parent_key_from_the_path_is_fixed(self):
        self.assertEqual(nest(CH_C, service(self.SVC % ("", "teamUid"))), set())

    def test_mismatch_comparison_is_fixed(self):
        chk = "    if (body.teamUid !== teamUid) throw new ForbiddenException();\n"
        self.assertEqual(nest(CH_C, service(self.SVC % (chk, "body.teamUid"))), set())

    def test_loop_item_parent_key_is_child_and_item_comparison_is_fixed(self):
        s = "  async addMembers(teamUid, body, user) {\n    await this.assertTeamLead(user, teamUid);\n%s    for (const row of body.rows) {\n      await this.prisma.teamMember.update({ where: { memberUid_teamUid: { memberUid: row.memberUid, teamUid: row.teamUid } }, data: {} });\n    }\n  }\n  async assertTeamLead(user, teamUid) {}"
        c = CH_C.replace("addMember(", "addMembers(")
        self.assertEqual(nest(c, service(s % "")), {("CHILD", "POST")})
        chk = "    if (body.rows.some((r) => r.teamUid !== teamUid)) throw new ForbiddenException();\n"
        self.assertEqual(nest(c, service(s % chk)), set())

    def test_sibling_reference_from_body_is_not_a_parent_key(self):
        s = service("  async addMember(teamUid, body, user) {\n    await this.assertTeamLead(user, teamUid);\n    return this.prisma.teamMember.create({ data: { memberUid: body.memberUid } });\n  }\n  async assertTeamLead(user, teamUid) {}")
        self.assertEqual(nest(CH_C, s), set())
        s = s.replace("memberUid: body.memberUid", "memberUid: body.memberUid, teamUid: body.teamUid")
        self.assertEqual(nest(CH_C, s), {("CHILD", "POST")})

    def test_route_without_a_path_parent_is_silent(self):
        c = CH_C.replace("':uid/members'", "'members'").replace("@Param('uid') teamUid: string, ", "")
        s = service("  async addMember(teamUid, body, user) {\n    return this.prisma.teamMember.create({ data: { teamUid: body.teamUid } });\n  }")
        self.assertEqual(nest(c.replace("addMember(teamUid, body", "addMember(body.teamUid, body"), s), set())


def js(path, text):
    return leads({path: text})


EXPRESS = "const router = require('express').Router();\nconst { prisma } = require('./db');\n\n"
NEXTH = "import { prisma } from '@/db';\nimport { getServerSession } from 'next-auth';\n\n"


class ExpressLeads(unittest.TestCase):
    P = "src/routes/widgets.js"

    def test_mass_body_role_written_is_mass_and_dropping_it_is_fixed(self):
        r = EXPRESS + "router.patch('/widgets/:id', requireAuth, async (req, res) => {\n  const { name, role } = req.body;\n  const w = await prisma.widget.update({ where: { id: req.params.id }, data: { %s } });\n  res.json(w);\n});\n"
        self.assertEqual(js(self.P, r % "name, role"), {("MASS", "PATCH")})
        self.assertEqual(js(self.P, r % "name"), set())
        self.assertEqual(js(self.P, (r % "...req.body").replace("const { name, role } = req.body", "const { role, ...rest } = req.body").replace("...req.body", "...rest")), set())

    def test_mass_across_orms(self):
        for call in ("Widget.findByIdAndUpdate(req.params.id, { name: req.body.name, role: req.body.role })", "Widget.update({ name: req.body.name, isAdmin: req.body.isAdmin }, { where: { id: req.params.id } })", "repo.save({ id: req.params.id, ...req.body, role: req.body.role })"):
            r = EXPRESS + "router.put('/widgets/:id', requireAuth, async (req, res) => {\n  await %s;\n  res.sendStatus(204);\n});\n" % call
            self.assertEqual({k for k, _ in js(self.P, r)}, {"MASS"}, call)
            self.assertEqual(js(self.P, r.replace("role: req.body.role", "x: 1").replace("isAdmin: req.body.isAdmin", "x: 1").replace(", ...req.body", "")), set(), call)

    def test_public_express_route_is_not_judged(self):
        r = EXPRESS + "router.patch('/widgets/:id', async (req, res) => {\n  const { name, role } = req.body;\n  await prisma.widget.update({ where: { id: req.params.id }, data: { name, role } });\n});\n"
        self.assertEqual(js(self.P, r), set())

    def test_idmix_where_on_body_id_after_check_on_path_id(self):
        r = EXPRESS + "router.patch('/projects/:projectId/items', requireAuth, async (req, res) => {\n  await assertCanEdit(req.user, req.params.projectId);\n  const item = await prisma.item.update({ where: { %s }, data: { name: req.body.name } });\n  res.json(item);\n});\n"
        self.assertEqual(js(self.P, r % "id: req.body.id"), {("IDMIX", "PATCH")})
        self.assertEqual(js(self.P, r % "id: req.body.id, projectId: req.params.projectId"), set())

    def test_child_parent_key_from_body(self):
        r = EXPRESS + "router.post('/teams/:teamId/members', requireAuth, async (req, res) => {\n  await assertTeamLead(req.user, req.params.teamId);\n%s  const m = await prisma.teamMember.create({ data: { memberUid: req.body.memberUid, teamId: %s } });\n  res.json(m);\n});\n"
        self.assertEqual(js(self.P, r % ("", "req.body.teamId")), {("CHILD", "POST")})
        self.assertEqual(js(self.P, r % ("", "req.params.teamId")), set())
        self.assertEqual(js(self.P, r % ("  if (req.body.teamId !== req.params.teamId) return res.sendStatus(403);\n", "req.body.teamId")), set())
        self.assertEqual(js(self.P, (r % ("", "req.body.teamId")).replace("teamId: req.body.teamId", "x: 1")), set())  # a body reference that is no parent key


class NextLeads(unittest.TestCase):
    A = "app/api/widgets/[id]/route.ts"
    B = "app/api/teams/[teamId]/members/route.ts"

    def test_mass_route_handler(self):
        r = NEXTH + "export async function PATCH(req: Request, { params }: { params: { id: string } }) {\n  const session = await getServerSession(authOptions);\n  const body = await req.json();\n  const { name, role } = body;\n  const w = await prisma.widget.update({ where: { id: params.id }, data: { %s } });\n  return Response.json(w);\n}\n"
        self.assertEqual(js(self.A, r % "name, role"), {("MASS", "PATCH")})
        self.assertEqual(js(self.A, r % "name"), set())
        self.assertEqual(js(self.A, (r % "...rest").replace("const { name, role } = body", "const { role, ...rest } = body")), set())
        self.assertEqual(js(self.A, r % "...body"), {("MASS", "PATCH")})

    def test_mass_post_put_verbs_and_pages_api(self):
        r = NEXTH + "export async function %s(req: Request, { params }: { params: { id: string } }) {\n  const session = await getServerSession(authOptions);\n  const { role } = await req.json();\n  await prisma.widget.update({ where: { id: params.id }, data: { role } });\n  return new Response(null);\n}\n"
        for v in ("POST", "PUT", "PATCH"):
            self.assertEqual({k for k, _ in js(self.A, r % v)}, {"MASS"}, v)
        self.assertEqual(js(self.A, r.replace("data: { role }", "data: { name: 'x' }") % "PUT"), set())
        pg = "import { prisma } from '@/db';\nimport { getServerSession } from 'next-auth';\n\nexport default async function handler(req, res) {\n  const session = await getServerSession(req, res, authOptions);\n  if (req.method !== 'PATCH') return res.status(405).end();\n  const { name, role } = req.body;\n  await prisma.widget.update({ where: { id: req.query.id }, data: { %s } });\n  res.json({ ok: true });\n}\n"
        self.assertEqual({k for k, _ in js("pages/api/widgets/[id].ts", pg % "name, role")}, {"MASS"})
        self.assertEqual(js("pages/api/widgets/[id].ts", pg % "name"), set())

    def test_idmix_route_handler(self):
        r = NEXTH + "export async function PATCH(req: Request, { params }: { params: { projectId: string } }) {\n  const session = await getServerSession(authOptions);\n  const body = await req.json();\n  await assertCanEdit(session.user, params.projectId);\n  const item = await prisma.item.update({ where: { %s }, data: { name: body.name } });\n  return Response.json(item);\n}\n"
        p = "app/api/projects/[projectId]/items/route.ts"
        self.assertEqual(js(p, r % "id: body.id"), {("IDMIX", "PATCH")})
        self.assertEqual(js(p, r % "id: body.id, projectId: params.projectId"), set())

    def test_child_route_handler(self):
        r = NEXTH + "export async function POST(req: Request, { params }: { params: { teamId: string } }) {\n  const session = await getServerSession(authOptions);\n  const body = await req.json();\n  await assertTeamLead(session.user, params.teamId);\n%s  const m = await prisma.teamMember.create({ data: { memberUid: body.memberUid, teamId: %s } });\n  return Response.json(m);\n}\n"
        self.assertEqual(js(self.B, r % ("", "body.teamId")), {("CHILD", "POST")})
        self.assertEqual(js(self.B, r % ("", "params.teamId")), set())
        self.assertEqual(js(self.B, r % ("  if (body.teamId !== params.teamId) return new Response(null, { status: 403 });\n", "body.teamId")), set())


class Revision(unittest.TestCase):
    """Each test fails before this change and passes after it."""
    P = "src/routes/widgets.js"

    def test_where_filter_on_a_body_value_is_not_written_data(self):
        r = EXPRESS + "router.patch('/widgets/:id', requireAuth, async (req, res) => {\n  const { name, role } = req.body;\n  await prisma.widget.update({ where: { id: req.params.id, ownerId: req.body.ownerId }, data: { name } });\n});\n"
        self.assertEqual(js(self.P, r), set())
        self.assertEqual(js(self.P, r.replace("data: { name }", "data: { name, role }")), {("MASS", "PATCH")})
        s = service("  update(uid, dto, user) {\n    return this.prisma.widget.update({ where: { uid, ownerUid: dto.ownerUid }, data: { name: dto.name } });\n  }")
        self.assertEqual(nest(MASS_C, s, DTO), set())

    def test_nest_direct_read_of_the_field_stays_silent(self):
        s = service("  update(uid, dto, user) {\n    return this.prisma.widget.update({ where: { uid }, data: { name: dto.name, role: dto.role } });\n  }")
        self.assertEqual(nest(MASS_C, s, DTO), set())

    def test_edit_check_before_the_write_is_mass_checked(self):
        r = EXPRESS + "router.patch('/widgets/:id', requireAuth, async (req, res) => {\n%s  const { name, role } = req.body;\n  await prisma.widget.update({ where: { id: req.params.id }, data: { name, role } });\n});\n"
        chk = "  if (!(await isMemberAllowedToEdit(req.user, req.params.id))) throw new ForbiddenException();\n"
        self.assertEqual(js(self.P, r % chk), {("MASS-CHECKED", "PATCH")})
        self.assertEqual(js(self.P, r % ""), {("MASS", "PATCH")})
        late = EXPRESS + "router.patch('/widgets/:id', requireAuth, async (req, res) => {\n  const { name, role } = req.body;\n  await prisma.widget.update({ where: { id: req.params.id }, data: { name, role } });\n" + chk + "});\n"
        self.assertEqual(js(self.P, late), {("MASS", "PATCH")})

    def test_semicolon_free_consequent_does_not_swallow_the_next_if(self):
        c = controller("""  @Put(':uid')
  @UseGuards(AcmeGuard)
  update(@Param('uid') uid: string, @Body() body, @Req() req) {
    if (body.isVerified) this.log(uid)
    if (!req.user) throw new ForbiddenException()
    return this.widgets.update(uid, body, req.user)
  }""")
        s = service("  update(uid, body, user) {\n    const data: any = {};\n    copyObj(body, data, ['name', 'isVerified']);\n    return this.prisma.widget.update({ where: { uid }, data });\n  }")
        self.assertEqual(nest(c, s), {("MASS", "PUT")})

    def test_admin_guard_demotes_mass_to_mass_admin(self):
        s = service("  update(uid, dto, user) {\n    return this.prisma.widget.update({ where: { uid }, data: dto });\n  }")
        for member, cls in ((MASS_C.replace("AcmeGuard", "AuthGuard, AdminGuard"), "MASS-ADMIN"), (MASS_C.replace("AcmeGuard", "AcmeGuard)\n  @UseGuards(SuperAdminGuard"), "MASS-ADMIN"), (MASS_C, "MASS")):
            self.assertEqual(nest(member, s, DTO), {(cls, "PATCH")})
        c = MASS_C.replace("@Controller('widgets')", "@Controller('widgets')\n@UseGuards(AuthGuard, AdminGuard)")
        self.assertEqual(nest(c, s, DTO), {("MASS-ADMIN", "PATCH")})  # class-level guard

    def test_express_query_is_client_chosen_but_pages_api_query_is_a_path_segment(self):
        r = EXPRESS + "router.patch('/projects/:projectId/items', requireAuth, async (req, res) => {\n  await assertCanEdit(req.user, req.params.projectId);\n  await prisma.item.update({ where: { id: req.query.id }, data: { name: req.body.name } });\n});\n"
        self.assertEqual(js(self.P, r), {("IDMIX", "PATCH")})
        self.assertEqual(js(self.P, r.replace("req.query.id", "req.params.id")), set())

    def test_bare_params_validation_is_no_access_check(self):
        r = EXPRESS + "router.patch('/projects/:projectId/items', requireAuth, async (req, res) => {\n  schema.validate(req.params);\n  await prisma.item.update({ where: { id: req.body.id }, data: { name: req.body.name } });\n});\n"
        self.assertEqual(js(self.P, r), set())
        self.assertEqual(js(self.P, r.replace("schema.validate(req.params)", "assertCanEdit(req.user, req.params.projectId)")), {("IDMIX", "PATCH")})

    def test_child_singularizes_plurals(self):
        for seg, key in (("addresses", "addressId"), ("categories", "categoryId"), ("people", "personId"), ("team-members", "teamMemberId")):
            r = EXPRESS + "router.post('/%s/:id/notes', requireAuth, async (req, res) => {\n  await assertCanEdit(req.user, req.params.id);\n  await prisma.note.create({ data: { text: req.body.text, %s: req.body.%s } });\n});\n" % (seg, key, key)
            self.assertEqual(js(self.P, r), {("CHILD", "POST")}, seg)

    def test_why_strings_name_req_body_and_req_params(self):
        out = raw("src/w.js", EXPRESS + "router.patch('/projects/:projectId/items', requireAuth, async (req, res) => {\n  await assertCanEdit(req.user, req.params.projectId);\n  await prisma.item.update({ where: { id: req.body.id }, data: { name: req.body.name } });\n});\n")
        self.assertIn("req.body.id", out)
        self.assertNotIn("__", out)

    def test_next_sibling_reference_is_not_a_parent_key(self):
        """Regression pin: passes before this change too."""
        r = NEXTH + "export async function POST(req: Request, { params }: { params: { teamId: string } }) {\n  const session = await getServerSession(authOptions);\n  const body = await req.json();\n  await assertTeamLead(session.user, params.teamId);\n  await prisma.teamMember.create({ data: { memberUid: body.memberUid } });\n}\n"
        self.assertEqual(js("app/api/teams/[teamId]/members/route.ts", r), set())


class Revision2(unittest.TestCase):
    """Six of eight fail before this change; the Admin-guard silence and the pages/api split are regression pins (they pass before it too)."""
    P = "src/routes/widgets.js"
    NEW = "import { Body, Controller, Post, UseGuards } from '@nestjs/common';\n"

    def create(self, data, guard="@UseGuards(AcmeGuard)", cls=""):
        c = self.NEW + "@Controller('widgets')\n%s\nexport class WidgetsController {\n  constructor(private readonly widgets: WidgetsService) {}\n\n  @Post()\n  %s\n  create(@Body() body: CreateWidgetDto) {\n    return this.widgets.create(body);\n  }\n}\n" % (cls, guard)
        s = service("  create(body) {\n    %s\n  }" % data)
        return nest(c, s, "export class CreateWidgetDto {\n  name: string;\n  authorMemberUid?: string;\n  authorTeamUid?: string;\n}\n")

    def test_positional_filter_is_not_written_data(self):
        for call in ("Widget.findOneAndUpdate({ _id: req.params.id, ownerId: req.body.ownerId }, { name: req.body.name })", "repo.update({ id: req.params.id, ownerId: req.body.ownerId }, { name: req.body.name })"):
            r = EXPRESS + "router.put('/widgets/:id', requireAuth, async (req, res) => {\n  await %s;\n  res.sendStatus(204);\n});\n" % call
            self.assertEqual(js(self.P, r), set(), call)
            self.assertEqual({k for k, _ in js(self.P, r.replace("name: req.body.name", "name: req.body.name, role: req.body.role"))}, {"MASS"}, call)

    def test_nest_owner_id_in_a_data_write_is_mass_but_a_filter_or_role_is_not(self):
        self.assertEqual(self.create("return this.prisma.widget.create({ data: { name: body.name, authorMemberUid: body.authorMemberUid ?? null } });"), {("MASS", "POST")})
        self.assertEqual(self.create("const { name, authorTeamUid } = body;\n    return this.prisma.widget.create({ data: { name, authorTeamUid } });"), {("MASS", "POST")})
        self.assertEqual(self.create("return this.prisma.widget.findMany({ where: { authorMemberUid: body.authorMemberUid } }) && this.prisma.widget.create({ data: { name: body.name } });"), set())
        self.assertEqual(self.create("return this.prisma.widget.create({ data: { name: body.name, authorMemberUid: this.me.uid } });"), set())

    def test_nest_owner_id_behind_an_admin_guard_stays_silent(self):
        d = "return this.prisma.widget.create({ data: { name: body.name, authorMemberUid: body.authorMemberUid } });"
        self.assertEqual(self.create(d, guard="@UseGuards(AuthGuard, AdminGuard)"), set())
        self.assertEqual(self.create(d, guard="", cls="@UseGuards(AdminGuard)"), set())

    def test_throw_in_the_else_branch_of_a_field_check_is_mass_checked(self):
        r = EXPRESS + "router.put('/widgets/:id', requireAuth, async (req, res) => {\n  const { name, createdBy } = req.body;\n  if (req.user.uid === createdBy) { ok(); } else { throw new ForbiddenException(); }\n  await prisma.widget.update({ where: { id: req.params.id }, data: { name, createdBy } });\n});\n"
        self.assertEqual(js(self.P, r), {("MASS-CHECKED", "PUT")})

    def test_access_check_row_says_it_does_not_name_the_field(self):
        r = EXPRESS + "router.patch('/widgets/:id', requireAuth, async (req, res) => {\n%s  const { name, role } = req.body;\n  await prisma.widget.update({ where: { id: req.params.id }, data: { name, role } });\n});\n"
        for chk, said in (("  if (!(await isMemberAllowedToEdit(req.user, req.params.id))) throw new ForbiddenException();\n", "does not name the field"), ("  if (role) throw new ForbiddenException();\n", "a check naming it is read")):
            self.assertIn(said, raw(self.P, r % chk))

    def test_child_accepts_shorthand_and_destructured_keys(self):
        r = EXPRESS + "router.post('/teams/:teamId/members', requireAuth, async (req, res) => {\n  await assertTeamLead(req.user, req.params.teamId);\n  const { teamId, memberUid } = req.body;\n  await prisma.teamMember.create({ data: { %s } });\n});\n"
        for data in ("memberUid, teamId", "memberUid, teamId: teamId"):
            self.assertEqual(js(self.P, r % data), {("CHILD", "POST")}, data)
        self.assertEqual(js(self.P, r % "memberUid"), set())
        self.assertEqual(js(self.P, (r % "memberUid, teamId").replace("const { teamId, memberUid } = req.body;", "const { memberUid } = req.body; const teamId = req.params.teamId;")), set())

    def test_pages_api_query_is_a_path_segment_and_express_query_is_not(self):
        """Regression pin: passes before this change too."""
        pg = "import { prisma } from '@/db';\nimport { getServerSession } from 'next-auth';\n\nexport default async function handler(req, res) {\n  const session = await getServerSession(req, res, authOptions);\n  if (req.method !== 'POST') return res.status(405).end();\n  await assertTeamLead(session.user, req.query.teamId);\n  await prisma.teamMember.create({ data: { memberUid: req.body.memberUid, teamId: %s } });\n}\n"
        self.assertEqual(js("pages/api/teams/[teamId]/members.ts", pg % "req.query.teamId"), set())
        self.assertEqual(js("pages/api/teams/[teamId]/members.ts", pg % "req.body.teamId"), {("CHILD", "POST")})
        r = EXPRESS + "router.post('/teams/:teamId/members', requireAuth, async (req, res) => {\n  await assertTeamLead(req.user, req.params.teamId);\n  await prisma.teamMember.create({ data: { memberUid: req.body.memberUid, teamId: req.query.teamId } });\n});\n"
        self.assertEqual(js(self.P, r), {("CHILD", "POST")})

    def test_cjs_handler_is_read(self):
        r = EXPRESS + "router.patch('/widgets/:id', requireAuth, async (req, res) => {\n  const { name, role } = req.body;\n  await prisma.widget.update({ where: { id: req.params.id }, data: { name, role } });\n});\n"
        self.assertEqual(js("src/routes/w.cjs", r), {("MASS", "PATCH")})


if __name__ == "__main__":
    unittest.main()
