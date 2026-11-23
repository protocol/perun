"""route_auth_map.py --privileged MASS, MASS-CHECKED, IDMIX and CHILD rows (authz_leads): an authenticated NestJS write whose client body reaches an ORM write
with a privileged field and no strip or pick (MASS, CWE-915), whose access check takes the path id while the write's where takes a body id (IDMIX), or whose
child row takes its parent key from the body with no tie to the path parent (CHILD, CWE-639). Each class has a positive fixture and a fixed negative, so
removing the fix turns the negative back into the positive. Fixtures are fictional (widgets, projects, teams, Acme)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/route_auth_map.py"
CLASSES = ("MASS", "MASS-CHECKED", "IDMIX", "CHILD")


def leads(files):
    """{(KIND, METHOD)} of the authz rows route_auth_map.py --privileged prints for files {relative path: text}."""
    with tempfile.TemporaryDirectory() as d:
        for rel, text in files.items():
            (Path(d) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(d) / rel).write_text(text)
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--privileged", d], capture_output=True, text=True, check=True)
    rows = [ln.split(":", 2)[2].split() for ln in r.stdout.splitlines()]
    return {(w[0][:-1], w[1]) for w in rows if w[0][:-1] in CLASSES}


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

    def test_route_without_a_path_parent_is_silent(self):
        c = CH_C.replace("':uid/members'", "'members'").replace("@Param('uid') teamUid: string, ", "")
        s = service("  async addMember(teamUid, body, user) {\n    return this.prisma.teamMember.create({ data: { teamUid: body.teamUid } });\n  }")
        self.assertEqual(nest(c.replace("addMember(teamUid, body", "addMember(body.teamUid, body"), s), set())


if __name__ == "__main__":
    unittest.main()
