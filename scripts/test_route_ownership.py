"""route_auth_map.py --privileged OWN and OWN-CHECKED rows: an authenticated NestJS write by client-sent id (plain verb decorators and ts-rest), or a
write of a client-sent owner id, is OWN when its controller member and the service method it calls never tie the write to the requester (CWE-639,
OWASP API1:2023), and OWN-CHECKED with the class of the check read (requester-compare, decorator-guard, machine) when they do. Positive: fixtures
that look like a check and are none stay OWN (a service that ignores the requester, audit and payload fields set from the requester, where keys
not set to the requester, words in strings, Swagger decorators, a 401 or 403, role words and helper calls in the body, a user guard beside a
machine guard). Checked: one fixture per check, firing on one row, so removing the check turns it back into OWN. Dropped: routes that are no
candidate (no write call, public, presence-check, unauthenticated, no id parameter, a PRIV row) print neither tier. NoCheck: compares with a
literal or between the client body and the record, a destructure default, a local `user` record, interceptors and pipes, and machine guards
beside a user guard all stay OWN, as do a role list naming a plain role, a requester-scoped where off the client id, an
Availability- or Capability-named guard, `uid` set to the requester, a client owner id under a local name and a reassigned shorthand key.
Plus the review_checks.sh --full rows: OWN as missing-ownership-check, OWN-CHECKED as ownership-check-read, a known misread kept as a row. Fixtures are fictional (Acme, example.com)."""
import inspect
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

S = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts"
SCRIPT, RC = S / "route_auth_map.py", S / "review_checks.sh"

CONTROLLER = """import { Body, Controller, Delete, Get, Param, Post, Put, Req, UseGuards } from '@nestjs/common';
import { AcmeTokenGuard } from './token.guard';
import { ThingsService } from './things.service';

@Controller('things')
export class ThingsController {
  constructor(private readonly things: ThingsService) {}

  @Get()
  @Public()
  list() { return this.things.list(); }

  @Put(':uid')
  @UseGuards(AcmeTokenGuard)
  update(@Param('uid') uid: string, @Body() dto: UpdateThingDto, @Req() req) {
    return this.things.update(uid, dto, req.user);
  }

  @Delete(':uid')
  @UseGuards(AcmeTokenGuard)
  remove(@Param('uid') uid: string, @Req() req) {
    return this.things.remove(uid, req.user);
  }

  @Post()
  @UseGuards(AcmeTokenGuard)
  create(@Body() dto: CreateThingDto, @Req() req) {
    return this.things.create(dto, req.user);
  }
}
"""
SERVICE = """import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from './prisma.service';

@Injectable()
export class ThingsService {
  constructor(private readonly prisma: PrismaService) {}

  list() {
    return this.prisma.thing.findMany({ select: { uid: true, title: true } });
  }

  async update(uid: string, dto: UpdateThingDto, requester: AcmeUser) {
    return this.prisma.thing.update({ where: { uid }, data: { title: dto.title } });
  }

  async remove(uid: string, requester: AcmeUser) {
    await this.prisma.thing.delete({ where: { uid } });
  }

  create(dto: CreateThingDto, requester: AcmeUser) {
    return this.prisma.thing.create({ data: { title: dto.title, owner: { connect: { uid: dto.ownerUid } } } });
  }
}
"""
CONTRACT = """import { initContract } from '@ts-rest/core';
const c = initContract();
export const acmeWidgets = c.router({
  listWidgets: { method: 'GET', path: '/v1/widgets', responses: { 200: c.type<unknown>() } },
  updateWidget: { method: 'PUT', path: '/v1/widgets/:uid', responses: { 200: c.type<unknown>() } },
});
"""
TSR_CONTROLLER = """import { Controller, UseGuards } from '@nestjs/common';
import { Api, TsRestRequest, initNestServer } from '@ts-rest/nest';
import { acmeWidgets } from './contract';
import { WidgetsService } from './widgets.service';
const server = initNestServer(acmeWidgets);

@Controller()
@UseGuards(AcmeTokenGuard)
export class WidgetsController {
  constructor(private widgets: WidgetsService) {}

  @Api(server.route.updateWidget)
  update(@TsRestRequest() { params, body }, @Req() req) {
    return this.widgets.rename(params.uid, body.title, req.user.uid);
  }
}
"""
TSR_SERVICE = """@Injectable()
export class WidgetsService {
  constructor(private readonly prisma: PrismaService) {}

  async rename(uid: string, title: string, requesterUid: string) {
    return this.prisma.widget.update({ where: { uid }, data: { title } });
  }
}
"""


def all_rows(files):
    """{(file, line, METHOD): (tier, message)} of the OWN and OWN-CHECKED rows route_auth_map.py --privileged prints for files {relative path: text}."""
    with tempfile.TemporaryDirectory() as d:
        for rel, text in files.items():
            (Path(d) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(d) / rel).write_text(text)
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--privileged", d], capture_output=True, text=True, check=True)
    out = {}
    for line in r.stdout.splitlines():
        f, ln, rest = line.split(":", 2)
        if rest.split()[0] in ("OWN:", "OWN-CHECKED:"): out[(f, int(ln), rest.split()[1])] = (rest.split()[0][:-1], rest)
    return out


def own_rows(files):
    """{(file, line, METHOD): message} of the OWN rows only."""
    return {k: m for k, (t, m) in all_rows(files).items() if t == "OWN"}


def nest(service=SERVICE, controller=CONTROLLER):
    return own_rows({"src/things/things.controller.ts": controller, "src/things/things.service.ts": service})


UPD = "    return this.prisma.thing.update({ where: { uid }, data: { title: dto.title } });\n"
FIND = "    const t = await this.prisma.thing.findUnique({ where: { uid } });\n"
SIG = "async update(uid: string, dto: UpdateThingDto, requester: AcmeUser) {"
MEMBER = "    return this.things.update(uid, dto, req.user);\n"
PUTGUARD = "  @Put(':uid')\n  @UseGuards(AcmeTokenGuard)\n"
ALL, NOPUT = ["DELETE", "POST", "PUT"], ["DELETE", "POST"]
NOSEMI = CONTROLLER.replace("{ AcmeTokenGuard }", "{ AcmeTokenGuard, InternalApiKeyGuard }").replace(";", "")  # no semicolons: the text before the class starts at the imports


def tiers(service=SERVICE, controller=CONTROLLER):
    """(sorted METHODs of the OWN rows, {METHOD: class} of the OWN-CHECKED rows) for the things fixture, after asserting the fixture text it was given was really edited."""
    assert (service, controller) != (SERVICE, CONTROLLER)
    rows = all_rows({"src/things/things.controller.ts": controller, "src/things/things.service.ts": service})
    return (sorted(k[2] for k, (t, _) in rows.items() if t == "OWN"),
            {k[2]: re.search(r"\(class=([\w-]+); match=", m)[1] for k, (t, m) in rows.items() if t == "OWN-CHECKED"})


def kinds(service=SERVICE, controller=CONTROLLER):
    """Sorted METHODs of the OWN rows for the things fixture (tiers())."""
    return tiers(service, controller)[0]


def put(body, t=kinds):
    """t() with the service update body UPD replaced by body; delete and create stay unchecked rows, so a check that drops every row fails."""
    return t(SERVICE.replace(UPD, body))


def put_member(line, t=kinds):
    """t() with line added to the controller update member before its service call."""
    return t(controller=CONTROLLER.replace(MEMBER, line + MEMBER))


class Positive(unittest.TestCase):
    def test_update_delete_and_owner_from_body(self):
        rows = nest()
        c = "src/things/things.controller.ts"
        self.assertEqual(sorted(rows), [(c, 13, "PUT"), (c, 19, "DELETE"), (c, 25, "POST")])
        self.assertIn("write by client-sent id", rows[(c, 13, "PUT")])
        self.assertIn("ThingsService.update", rows[(c, 13, "PUT")])
        self.assertIn("ids listed by GET /things auth=public", rows[(c, 13, "PUT")])
        self.assertIn("client-sent owner id written", rows[(c, 25, "POST")])

    def test_orm_write_verbs(self):
        # Mongoose, MikroORM and TypeORM write calls beyond update / delete / save still make the PUT and DELETE rows
        rm = "    await this.prisma.thing.delete({ where: { uid } });\n"
        for orm, upd, rem in (("mongoose", "this.thingModel.findByIdAndUpdate(uid, dto)", "this.thingModel.findOneAndDelete({ _id: uid })"),
                              ("mongoose-bulk", "this.thingModel.replaceOne({ _id: uid }, dto)", "this.thingModel.bulkWrite([{ deleteOne: { filter: { _id: uid } } }])"),
                              ("mikro-orm", "this.em.nativeUpdate(Thing, { uid }, dto)", "this.em.nativeDelete(Thing, { uid })"),
                              ("typeorm", "this.repo.increment({ uid }, 'views', 1)", "this.repo.softRemove({ uid })"),
                              ("mongoose-one", "this.thingModel.findOneAndUpdate({ _id: uid }, dto)", "this.thingModel.findByIdAndDelete(uid)"),
                              ("mongoose-replace", "this.thingModel.findOneAndReplace({ _id: uid }, dto)", "this.thingModel.findByIdAndRemove(uid)"),
                              ("mikro-orm-flush", "this.em.persistAndFlush(dto)", "this.repo.decrement({ uid }, 'views', 1)"),
                              ("sequelize-bulk", "this.thingModel.bulkCreate([dto])", "this.thingModel.destroy({ where: { uid } })")):
            with self.subTest(orm):
                self.assertEqual(kinds(SERVICE.replace(UPD, "    return %s;\n" % upd).replace(rm, "    await %s;\n" % rem)), ALL)

    def test_branded_id_type_and_shadowing_parameter(self):
        # a `UserId` type annotation is no requester-id assignment, and a later parameter named like the field does not retype it
        svc = SERVICE.replace("requester: AcmeUser) {\n    return", "requesterUid: UserId) {\n    return")
        ctl = CONTROLLER.replace("list() { return", "list(@Query('q') things: string) { return")
        rows = nest(svc, ctl)
        self.assertIn("ThingsService.update", rows[("src/things/things.controller.ts", 13, "PUT")])

    def test_tsrest_member_with_class_guard(self):
        rows = own_rows({"src/contract.ts": CONTRACT, "src/widgets.controller.ts": TSR_CONTROLLER, "src/widgets.service.ts": TSR_SERVICE})
        self.assertEqual(list(rows), [("src/widgets.controller.ts", 12, "PUT")])
        self.assertIn("/v1/widgets/:uid auth=UseGuards(AcmeTokenGuard)", rows[("src/widgets.controller.ts", 12, "PUT")])
        self.assertIn("WidgetsService.rename", rows[("src/widgets.controller.ts", 12, "PUT")])

    def test_field_set_from_requester_is_no_check(self):
        # an audit field written from the requester's id ties neither a write by client-sent id nor a client-sent owner id to the requester
        svc = SERVICE.replace(UPD, UPD.replace("title: dto.title", "title: dto.title, updatedBy: requester.uid")).replace(
            "title: dto.title, owner:", "title: dto.title, createdBy: requester.uid, owner:")
        self.assertEqual(kinds(svc), ALL)

    def test_where_key_needs_the_requester_id(self):
        self.assertEqual(put(UPD.replace("where: { uid }", "where: { uid, username: dto.username }")), ALL)

    def test_member_id_is_not_me(self):
        self.assertEqual(put(UPD.replace("where: { uid }", "where: { uid, ownerUid: memberId }")), ALL)

    def test_bare_user_or_author_id_is_not_the_requester(self):
        for v in ("userId", "authorId"):
            with self.subTest(v=v): self.assertEqual(put(UPD.replace("where: { uid }", "where: { uid, ownerUid: %s }" % v)), ALL)

    def test_untied_shorthand_owner_key(self):
        self.assertEqual(put(UPD.replace("where: { uid }", "where: { uid, ownerUid }")), ALL)

    def test_owner_field_set_in_write_payload_is_no_check(self):
        svc = SERVICE.replace(SIG, SIG.replace("requester", "user")).replace(UPD, UPD.replace("title: dto.title", "title: dto.title, ownerId: user.id, userId: user.id"))
        self.assertEqual(kinds(svc), ALL)

    def test_user_or_machine_guard_has_a_user(self):
        self.assertEqual(kinds(controller=CONTROLLER.replace(PUTGUARD, PUTGUARD.replace("AcmeTokenGuard", "AcmeJwtOrApiKeyGuard"))), ALL)

    def test_machine_guard_import_is_no_class_guard(self):
        self.assertEqual(kinds(controller=NOSEMI), ALL)

    def test_return_type_is_not_the_body(self):
        rows = nest(SERVICE.replace(SIG, SIG[:-2] + ": Promise<{ uid: string; title: string }> {"))
        self.assertIn("ThingsService.update", rows[("src/things/things.controller.ts", 13, "PUT")])

    def test_member_return_type_is_not_the_body(self):
        # a controller member's object return type closes no member: its body (and the service call in it) is still read
        self.assertEqual(kinds(controller=CONTROLLER.replace("@Req() req) {\n" + MEMBER, "@Req() req): Promise<{ ok: boolean }> {\n" + MEMBER)), ALL)

    def test_service_name_in_two_files(self):
        # two @Injectable classes of one name: both are read, so the rows stay
        dup = "@Injectable()\nexport class ThingsService {\n  list() { return []; }\n}\n"
        rows = own_rows({"src/things/things.controller.ts": CONTROLLER, "src/things/things.service.ts": SERVICE, "src/legacy/things.service.ts": dup})
        self.assertEqual(sorted(k[2] for k in rows), ALL)

    def test_api_key_guard_is_no_machine(self):
        # a bare or org API key guard is often a user's or an org's key: only internal, service, integration, machine or M2M names are machine guards
        for g in ("AcmeApiKeyGuard", "AcmeOrgApiKeyGuard"):
            with self.subTest(g): self.assertEqual(tiers(controller=CONTROLLER.replace(PUTGUARD, PUTGUARD.replace("AcmeTokenGuard", g))), (ALL, {}))

    def test_service_word_is_no_role_check(self):
        self.assertEqual(put(UPD.replace("title: dto.title", "title: dto.title, availability: dto.availability, capability: 1")), ALL)

    def test_string_literal_is_no_check(self):
        # a route path, a controller prefix or a log line names words, it checks nothing
        for ctl, svc in ((CONTROLLER.replace("@Controller('things')", "@Controller('policies')"), SERVICE),
                         (CONTROLLER.replace("@Put(':uid')", "@Put(':uid/availability')"), SERVICE),
                         (CONTROLLER, SERVICE.replace(UPD, "    this.log('requester.uid !== t.ownerUid');\n" + UPD))):
            with self.subTest(ctl=ctl[:60], svc=svc[-200:]): self.assertEqual(kinds(svc, ctl), ALL)

    def test_swagger_decorator_is_no_check(self):
        for d in ("@ApiForbiddenResponse({ description: 'Not yours' })", "@ApiResponse({ status: 403 })", "@ApiUnauthorizedResponse()",
                  "@ApiAdminOperation({ summary: 'Rename a thing' })"):
            with self.subTest(d=d): self.assertEqual(kinds(controller=CONTROLLER.replace(PUTGUARD, PUTGUARD + "  " + d + "\n")), ALL)

    def test_unauthorized_is_no_check(self):
        # a 401 says the caller is unknown; it never compares the caller to the owner
        self.assertEqual(put_member("    if (!req.user) throw new UnauthorizedException();\n"), ALL)

    def test_body_role_word_is_no_check(self):
        # a role or policy word in the member body, signature or service call is a name, not a guard (ROLECHK reads decorators only)
        ctls = (CONTROLLER.replace("private readonly things:", "private readonly policies:").replace("this.things.", "this.policies."),
                CONTROLLER.replace("UpdateThingDto", "UpdatePolicyDto"),
                CONTROLLER.replace("  update(@Param", "  updateAvailability(@Param").replace(MEMBER, MEMBER.replace(".update(", ".updateAvailability(")),
                CONTROLLER.replace(MEMBER, MEMBER.replace("dto,", "dto.capabilities,")),
                CONTROLLER.replace(MEMBER, "    if (!req.user.roles.includes('editor')) throw new NotFoundException();\n" + MEMBER))
        svcs = (SERVICE, SERVICE, SERVICE.replace(SIG, SIG.replace("update(", "updateAvailability(")), SERVICE, SERVICE)
        for ctl, svc in zip(ctls, svcs):
            with self.subTest(ctl=ctl[ctl.index("@Put"):][:400]): self.assertEqual(kinds(svc, ctl), ALL)

    def test_helper_call_is_no_check(self):
        # a helper call reads as no check whatever its name: only a requester comparison the scan can see suppresses the row
        for body in ("    const p = mapPolicy(dto);\n", "    await this.acl.changeOwner(uid, dto.ownerUid);\n", "    await this.checkAvailability(uid);\n",
                     FIND + "    if (!this.hasOwner(t)) throw new NotFoundException();\n", "    if (isPolicyExpired(dto)) return null;\n",
                     "    await this.acl.assertOwner(uid, requester);\n", "    await this.acl.canAccess(uid, requester);\n", "    await this.acl.authorize(uid, requester);\n"):
            with self.subTest(body=body): self.assertEqual(put(body + UPD), ALL)
        self.assertEqual(kinds(SERVICE.replace("  create(dto: CreateThingDto, requester: AcmeUser) {\n",
                                               "  async create(dto: CreateThingDto, requester: AcmeUser) {\n    await this.ensureOwnerExists(dto.ownerUid);\n")), ALL)
        for line in ("    this.tokens.verifyAccessToken(req.headers.authorization);\n", "    if (!belongsTo(uid, req.user)) throw new NotFoundException();\n"):
            with self.subTest(line=line): self.assertEqual(put_member(line), ALL)

    def test_forbidden_is_no_check(self):
        # a 403 for any reason other than a requester comparison (a title length, a closed record, a missing record) checks nothing about the owner
        for body in ("    if (dto.title.length > 99) throw new ForbiddenException('too long');\n",
                     FIND + "    if (t.status === 'closed') throw new ForbiddenException();\n", FIND + "    if (!t) throw new ForbiddenException();\n"):
            with self.subTest(body=body): self.assertEqual(put(body + UPD), ALL)

    def test_member_and_service_names_are_no_call(self):
        # the route member's own declaration, with or without a return type, and the service method's signature are no guard call
        for sig in ("", ": Promise<Thing>"):
            ctl = CONTROLLER.replace("  update(@Param('uid') uid: string, @Body() dto: UpdateThingDto, @Req() req) {",
                                     "  verifyOwnership(@Param('uid') uid: string, @Body() dto: UpdateThingDto, @Req() req)%s {" % sig)
            with self.subTest(sig=sig): self.assertEqual(kinds(controller=ctl), ALL)
        ctl = CONTROLLER.replace(MEMBER, MEMBER.replace(".update(", ".transferOwnership("))
        self.assertEqual(kinds(SERVICE.replace(SIG, SIG.replace("update(", "transferOwnership(")), ctl), ALL)

    def test_owner_words_shared_with_sibling_check(self):
        sys.path.insert(0, str(S))
        import ownership_sibling_check as o
        import route_auth_map as r
        self.assertIn(o.OWNER_WORDS, o.OWN_ATTR.pattern)
        self.assertIn("owner_checks(OWNER_WORDS)", inspect.getsource(r.ownership))
        for p in r.owner_checks("zzword"): self.assertIn("zzword", p.pattern)


CMPD, DG, MC = "requester-compare", "decorator-guard", "machine"
CREATE = "create(dto: CreateThingDto, requester: AcmeUser) {\n"
PARAMS = "@Body() dto: UpdateThingDto, @Req() req"


class Checked(unittest.TestCase):
    """One fixture per check: only that check fires, and only on the PUT row, so the row is OWN-CHECKED with that class and removing the check brings it back as OWN."""

    def test_owner_compared_left(self):
        self.assertEqual(put(FIND + "    if (requester.uid !== t.holder) throw new NotFoundException();\n" + UPD, tiers), (NOPUT, {"PUT": CMPD}))

    def test_owner_compared_right(self):
        self.assertEqual(put(FIND + "    if (t.holder !== requester.uid) throw new NotFoundException();\n" + UPD, tiers), (NOPUT, {"PUT": CMPD}))

    def test_match_names_the_check(self):
        svc = SERVICE.replace(UPD, FIND + "    if (requester.uid !== t.holder) throw new NotFoundException();\n" + UPD)
        rows = all_rows({"src/things/things.controller.ts": CONTROLLER, "src/things/things.service.ts": svc})
        self.assertEqual([m for t, m in rows.values() if t == "OWN-CHECKED"],
                         [" OWN-CHECKED: PUT /things/:uid auth=UseGuards(AcmeTokenGuard) (class=requester-compare; match=requester.uid !== t.holder)"])

    def test_same_class_helper_check(self):
        svc = SERVICE.replace("    await this.prisma.thing.delete(", "    await this.assertOwned(uid, requester);\n    await this.prisma.thing.delete(").replace(
            "  list() {", "  private async assertOwned(uid: string, requester: AcmeUser) {\n"
            "    const t = await this.prisma.thing.findUnique({ where: { uid } });\n    if (t.ownerUid !== requester.uid) throw new NotFoundException();\n  }\n\n  list() {")
        self.assertEqual(tiers(svc), (["POST", "PUT"], {"DELETE": CMPD}))

    def test_where_scoped_to_requester(self):
        self.assertEqual(put(UPD.replace("where: { uid }", "where: { uid, ownerUid: requester.uid }"), tiers), (NOPUT, {"PUT": CMPD}))

    def test_where_scoped_to_requester_object(self):
        self.assertEqual(put(UPD.replace("where: { uid }", "where: { uid, ownerUid: auth.uid }"), tiers), (NOPUT, {"PUT": CMPD}))

    def test_where_user_id_set_to_caller(self):
        svc = SERVICE.replace(SIG, SIG.replace("requester", "user")).replace(UPD, UPD.replace("where: { uid }", "where: { uid, userId: user.id }"))
        self.assertEqual(tiers(svc), (NOPUT, {"PUT": CMPD}))

    def test_lookup_of_the_record_scoped_to_requester(self):
        self.assertEqual(put("    const t = await this.prisma.thing.findFirst({ where: { uid, ownerUid: requester.uid } });\n"
                             "    if (!t) throw new NotFoundException();\n" + UPD, tiers), (NOPUT, {"PUT": CMPD}))

    def test_owner_compared_optional_chain(self):
        self.assertEqual(put(FIND + "    if (requester?.uid !== t?.holder) throw new NotFoundException();\n" + UPD, tiers), (NOPUT, {"PUT": CMPD}))

    def test_requester_copied_from_the_request(self):
        # `const user = req.user` keeps the requester; only a local loaded from anything else is a record
        self.assertEqual(put_member("    const user = req.user;\n    if (user.id !== uid) throw new NotFoundException();\n", tiers), (NOPUT, {"PUT": CMPD}))

    def test_where_shorthand_owner_key_assigned_from_requester(self):
        self.assertEqual(put("    const ownerUid = requester.uid;\n" + UPD.replace("where: { uid }", "where: { uid, ownerUid }"), tiers), (NOPUT, {"PUT": CMPD}))

    def test_requester_pk_compared(self):
        self.assertEqual(put_member("    if (req.user.pk !== uid) throw new NotFoundException();\n", tiers), (NOPUT, {"PUT": CMPD}))

    def test_user_decorator_parameter_is_the_requester(self):
        ctl = CONTROLLER.replace(PARAMS, PARAMS.replace("@Req() req", "@CurrentUser() member: AcmeUser")).replace(
            MEMBER, "    if (member.uid !== uid) throw new NotFoundException();\n    return this.things.update(uid, dto, member);\n")
        self.assertEqual(tiers(controller=ctl), (NOPUT, {"PUT": CMPD}))

    def test_client_owner_compared_to_requester_on_create(self):
        # a create with no record id in the path: the client-sent owner id compared to the requester is the check
        self.assertEqual(tiers(SERVICE.replace(CREATE, CREATE + "    if (dto.ownerUid !== requester.uid) throw new NotFoundException();\n")), (["DELETE", "PUT"], {"POST": CMPD}))

    def test_authz_decorator(self):
        self.assertEqual(tiers(controller=CONTROLLER.replace(PUTGUARD, PUTGUARD + "  @Roles('admin')\n")), (NOPUT, {"PUT": DG}))

    def test_role_decorator_on_member_and_class(self):
        # ROLECHK alone (no OWNCHK name): a staff-only decorator on the member, then on the class
        self.assertEqual(tiers(controller=CONTROLLER.replace(PUTGUARD, PUTGUARD + "  @StaffOnly()\n")), (NOPUT, {"PUT": DG}))
        self.assertEqual(tiers(controller=CONTROLLER.replace("@Controller('things')", "@Controller('things')\n@StaffOnly()")), ([], dict.fromkeys(ALL, DG)))

    def test_policy_decorator_and_guard(self):
        for name, ctl in (("check policies", CONTROLLER.replace(PUTGUARD, PUTGUARD + "  @CheckPolicies((a) => a.can(Action.Update, Thing))\n")),
                          ("policies guard", CONTROLLER.replace(PUTGUARD, PUTGUARD.replace("AcmeTokenGuard", "AcmeTokenGuard, PoliciesGuard"))),
                          ("casl guard", CONTROLLER.replace(PUTGUARD, PUTGUARD.replace("AcmeTokenGuard", "AcmeTokenGuard, CaslAbilityGuard")))):
            with self.subTest(name): self.assertEqual(tiers(controller=ctl), (NOPUT, {"PUT": DG}))

    def test_owner_guard_on_member_and_class(self):
        self.assertEqual(tiers(controller=CONTROLLER.replace(PUTGUARD, PUTGUARD.replace("AcmeTokenGuard", "OwnerGuard"))), (NOPUT, {"PUT": DG}))
        self.assertEqual(tiers(controller=CONTROLLER.replace("@Controller('things')", "@Controller('things')\n@UseGuards(OwnerGuard)")), ([], dict.fromkeys(ALL, DG)))

    def test_authz_guard_name(self):
        self.assertEqual(tiers(controller=CONTROLLER.replace(PUTGUARD, PUTGUARD.replace("AcmeTokenGuard", "AcmeTokenGuard, AcmeOwnerGuard"))), (NOPUT, {"PUT": DG}))

    def test_admin_guard(self):
        self.assertEqual(tiers(controller=CONTROLLER.replace("@UseGuards(AcmeTokenGuard)", "@UseGuards(AcmeTokenGuard, AcmeAdminGuard)")), ([], dict.fromkeys(ALL, DG)))

    def test_machine_guard_built_with_new(self):
        self.assertEqual(tiers(controller=CONTROLLER.replace(PUTGUARD, PUTGUARD.replace("AcmeTokenGuard", "new AcmeInternalKeyGuard()"))), (NOPUT, {"PUT": MC}))

    def test_machine_credential_guard(self):
        ctl = CONTROLLER.replace(PUTGUARD, PUTGUARD.replace("AcmeTokenGuard", "AcmeInternalAuthGuard")).replace(
            "  @Delete(':uid')\n  @UseGuards(AcmeTokenGuard)", "  @Delete(':uid')\n  @UseGuards(AcmeIntegrationKeyGuard)")
        self.assertEqual(tiers(controller=ctl), (["POST"], {"PUT": MC, "DELETE": MC}))

    def test_machine_guard_on_semicolonless_class(self):
        # every guard a machine guard: the class guard of a semicolon-less controller, members with none of their own
        ctl = NOSEMI.replace("@Controller('things')", "@Controller('things')\n@UseGuards(InternalApiKeyGuard)").replace("  @UseGuards(AcmeTokenGuard)\n", "")
        self.assertEqual(tiers(controller=ctl), ([], dict.fromkeys(ALL, MC)))


class Dropped(unittest.TestCase):
    """Routes that are no ownership candidate print neither OWN nor OWN-CHECKED; the PUT row goes, DELETE and POST stay OWN."""

    def test_no_write_call(self):
        self.assertEqual(put("    return this.prisma.thing.findUnique({ where: { uid } });\n", tiers), (NOPUT, {}))

    def test_read_calls_named_like_writes(self):
        # reads whose names share a write verb's prefix make no PUT row
        for read in ("this.thingModel.findAndCount({ uid })", "this.db.bulkGet([uid])", "this.store.persistence(uid)", "this.sync.incrementalSync(uid)"):
            with self.subTest(read): self.assertEqual(put("    return %s;\n" % read), NOPUT)

    def test_unauthenticated_route_is_route_auth_not_ownership(self):
        anon = CONTROLLER.replace("  @UseGuards(AcmeTokenGuard)\n", "").replace(", @Req() req", "").replace(", req.user", "")
        self.assertEqual(tiers(controller=anon), ([], {}))

    def test_public_member_is_route_auth_not_ownership(self):
        self.assertEqual(tiers(controller=CONTROLLER.replace(PUTGUARD, "  @Put(':uid')\n  @Public()\n")), (NOPUT, {}))

    def test_presence_check_is_route_auth_not_ownership(self):
        m = "  update(@Param('uid') uid: string, @Body() dto: UpdateThingDto, @Req() req) {\n" + MEMBER
        ctl = CONTROLLER.replace(PUTGUARD, "  @Put(':uid')\n").replace(m, "  update(@Param('uid') uid: string, @Body() dto: UpdateThingDto, @Res() res) {\n"
                                                                       "    if (!dto) return res.status(401).send();\n    return this.things.update(uid, dto);\n")
        self.assertEqual(tiers(controller=ctl), (NOPUT, {}))

    def test_write_without_id_param(self):
        # a PUT on the collection path takes no record id from the path, and its service writes no client-sent owner id
        self.assertEqual(tiers(controller=CONTROLLER.replace("@Put(':uid')", "@Put()")), (NOPUT, {}))

    def test_unscanned_service_call_is_the_write(self):
        # with no service body to read, the member's `this.things.update(` is the write; the create sends no owner id
        self.assertEqual(sorted(k[2] for k in own_rows({"src/things/things.controller.ts": CONTROLLER})), ["DELETE", "PUT"])

    def test_priv_row_is_not_repeated(self):
        self.assertEqual(tiers(controller=CONTROLLER.replace("@Put(':uid')", "@Put('users/:uid')")), (NOPUT, {}))


class NoCheck(unittest.TestCase):
    """Text that looks like a check and is none: every row stays OWN, none is OWN-CHECKED."""

    def test_literal_compare(self):
        # the owner or the requester compared to null, or a create checking the client sent an owner id
        for name, svc, ctl in (
                ("owner null", SERVICE.replace(UPD, FIND + "    if (t.ownerUid === null) throw new NotFoundException();\n" + UPD), CONTROLLER),
                ("create null", SERVICE.replace(CREATE, CREATE + "    if (dto.ownerUid == null) throw new BadRequestException();\n"), CONTROLLER),
                ("requester null", SERVICE, CONTROLLER.replace(MEMBER, "    if (req.user.id == null) throw new UnauthorizedException();\n" + MEMBER)),
                ("named constant", SERVICE.replace(UPD, "    if (requester.uid === SYSTEM_UID) throw new ForbiddenException();\n" + UPD), CONTROLLER),
                ("requester twice", SERVICE, CONTROLLER.replace(MEMBER, "    if (req.user.sub !== session.uid) throw new UnauthorizedException();\n" + MEMBER))):
            with self.subTest(name): self.assertEqual(tiers(svc, ctl), (ALL, {}))

    def test_client_owner_compared_to_record(self):
        # a transfer comparing the client-sent owner id to the record's checks nothing about the requester
        self.assertEqual(put(FIND + "    if (dto.ownerUid !== t.ownerUid) await this.prisma.audit.create({ data: { uid } });\n" + UPD, tiers), (ALL, {}))

    def test_client_owner_compared_to_requester_on_record_path(self):
        # a record id in the path: the client-sent owner id compared to the requester checks the new owner, not the record's
        self.assertEqual(put("    if (dto.ownerUid !== requester.uid) throw new NotFoundException();\n" + UPD, tiers), (ALL, {}))

    def test_user_guard_beside_a_machine_guard(self):
        # one user guard, on the member before or after the machine guard or beside a machine class guard, keeps the requester
        for name, ctl in (("key first", CONTROLLER.replace(PUTGUARD, PUTGUARD.replace("AcmeTokenGuard", "AcmeInternalKeyGuard, AcmeJwtAuthGuard"))),
                          ("user first", CONTROLLER.replace(PUTGUARD, PUTGUARD.replace("AcmeTokenGuard", "AcmeJwtAuthGuard, AcmeInternalKeyGuard"))),
                          ("class key", CONTROLLER.replace("@Controller('things')", "@Controller('things')\n@UseGuards(AcmeInternalKeyGuard)")),
                          ("semicolon-less class key", NOSEMI.replace("@Controller('things')", "@Controller('things')\n@UseGuards(InternalApiKeyGuard)"))):
            with self.subTest(name): self.assertEqual(tiers(controller=ctl), (ALL, {}))

    def test_destructure_default_is_no_shorthand_check(self):
        # `{ ownerUid = requester.uid } = dto`, on one line or several: the client's value wins
        for d in ("    const { ownerUid = requester.uid } = dto;\n", "    const {\n      ownerUid = requester.uid\n    } = dto;\n"):
            with self.subTest(d=d): self.assertEqual(put(d + UPD.replace("where: { uid }", "where: { uid, ownerUid }"), tiers), (ALL, {}))

    def test_where_on_another_row_is_no_scope(self):
        # a bare id or pk set to the requester's id names the requester's own row, and a where on another model scopes nothing about the record written
        usr = SERVICE.replace(SIG, SIG.replace("requester", "user"))
        for name, svc in (("own row", usr.replace(UPD, "    const me = await this.prisma.user.findUnique({ where: { id: user.id } });\n" + UPD)),
                          ("bare id on the write", usr.replace(UPD, UPD.replace("where: { uid }", "where: { uid, id: user.id }"))),
                          ("other model", SERVICE.replace(UPD, "    const sub = await this.prisma.subscription.findFirst({ where: { userId: requester.uid } });\n" + UPD))):
            with self.subTest(name): self.assertEqual(tiers(svc), (ALL, {}))

    def test_non_privileged_role_is_no_check(self):
        # a plain user role or a bare roles guard says who may call, not whose record it is
        for name, ctl in (("user role", CONTROLLER.replace(PUTGUARD, PUTGUARD + "  @Roles('user')\n")),
                          ("roles guard", CONTROLLER.replace(PUTGUARD, PUTGUARD.replace("AcmeTokenGuard", "RolesGuard"))),
                          ("token and roles guard", CONTROLLER.replace(PUTGUARD, PUTGUARD.replace("AcmeTokenGuard", "AcmeTokenGuard, RolesGuard")))):
            with self.subTest(name): self.assertEqual(tiers(controller=ctl), (ALL, {}))

    def test_user_record_is_not_the_requester(self):
        body = "    const user = await this.prisma.user.findUnique({ where: { email: dto.email } });\n" + UPD.replace("where: { uid }", "where: { uid, ownerUid: user.uid }")
        self.assertEqual(put(body, tiers), (ALL, {}))

    def test_non_guard_decorator_is_no_guard(self):
        # interceptors, pipes and parameter decorators check nothing, whatever their names say
        for name, ctl in (("class", CONTROLLER.replace("@Controller('things')", "@Controller('things')\n@UseInterceptors(ObservabilityInterceptor)")),
                          ("policy", CONTROLLER.replace(PUTGUARD, PUTGUARD + "  @UseInterceptors(RetryPolicyInterceptor)\n")),
                          ("staff", CONTROLLER.replace(PUTGUARD, PUTGUARD + "  @UseInterceptors(StaffAuditInterceptor)\n")),
                          ("pipe", CONTROLLER.replace(PUTGUARD, PUTGUARD + "  @UsePipes(AdminRoleValidationPipe)\n")),
                          ("parameter", CONTROLLER.replace(PARAMS, PARAMS + ", @CurrentOwner() owner: AcmeUser"))):
            with self.subTest(name): self.assertEqual(tiers(controller=ctl), (ALL, {}))


    def test_mixed_role_list_is_no_check(self):
        # any listed role may call, so a role list with one plain role says nothing about whose record it is
        for d in ("  @Roles('user', 'admin')\n", "  @Roles(Role.User, Role.Admin)\n"):
            with self.subTest(d=d): self.assertEqual(tiers(controller=CONTROLLER.replace(PUTGUARD, PUTGUARD + d)), (ALL, {}))

    def test_requester_where_off_the_client_id_is_no_scope(self):
        # a where scoped to the requester counts only on the model written by the client id and only when it names that id
        for name, body in (("another written model", "    await this.prisma.notification.updateMany({ where: { userId: requester.uid }, data: { seen: true } });\n"),
                           ("same model without the id", "    const t = await this.prisma.thing.findFirst({ where: { ownerUid: requester.uid } });\n"
                                                         "    if (!t) throw new NotFoundException();\n")):
            with self.subTest(name): self.assertEqual(put(body + UPD, tiers), (ALL, {}))

    def test_ability_word_inside_a_name_is_no_policy_guard(self):
        # `Availability` and `Capability` hold "ability" but name no policy or CASL guard
        for g in ("AvailabilityGuard", "CapabilityGuard"):
            with self.subTest(g): self.assertEqual(tiers(controller=CONTROLLER.replace(PUTGUARD, PUTGUARD.replace("AcmeTokenGuard", "AcmeTokenGuard, " + g))), (ALL, {}))

    def test_uid_set_to_requester_is_own_row(self):
        # `where: { uid: requester.uid }` loads the requester's own row (here on a create, where no path id narrows the where), not an owner check
        body = "    await this.prisma.user.update({ where: { uid: requester.uid }, data: { lastActive: 1 } });\n"
        self.assertEqual(tiers(SERVICE.replace(CREATE, CREATE + body)), (ALL, {}))

    def test_client_owner_alias_compared_on_record_path(self):
        # `const { ownerUid } = dto` is the client's value under another name: on a record path it checks the new owner, not the record's
        for d in ("    const { ownerUid } = dto;\n", "    const { owner: ownerUid } = dto;\n", "    const ownerUid = dto.ownerUid;\n"):
            with self.subTest(d=d): self.assertEqual(put(d + "    if (ownerUid !== requester.uid) throw new NotFoundException();\n" + UPD, tiers), (ALL, {}))

    def test_reassigned_shorthand_owner_key_is_no_check(self):
        # a shorthand owner key declared from the requester and then assigned the client's value scopes to the client's value
        body = "    let ownerUid = requester.uid;\n    ownerUid = dto.ownerUid;\n" + UPD.replace("where: { uid }", "where: { uid, ownerUid }")
        self.assertEqual(put(body, tiers), (ALL, {}))

def hub(service=SERVICE):
    """[(file, line, rule, msg)] of the tool `ownership` rows review_checks.sh --full reports for the things fixture with the given service."""
    env = dict(os.environ, PATH="/usr/bin:/bin")
    with tempfile.TemporaryDirectory() as d:
        for rel, text in (("src/things.controller.ts", CONTROLLER), ("src/things.service.ts", service)):
            (Path(d) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(d) / rel).write_text(text)
        for a in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@example.com", "-c", "user.name=Acme", "commit", "-qm", "fixture"]):
            subprocess.run(["git", "-C", d, *a], check=True, capture_output=True, env=env)
        r = subprocess.run(["bash", str(RC), "--full", "--repo", d], capture_output=True, text=True, env=env)
    return sorted((x["file"], x["line"], x["rule"], x["message"]) for x in json.loads(r.stdout) if x["tool"] == "ownership")


class HubRow(unittest.TestCase):
    def test_review_checks_full_row(self):
        self.assertEqual([r[:3] for r in hub()], [("src/things.controller.ts", n, "missing-ownership-check") for n in (13, 19, 25)])

    def test_checked_route_is_a_row(self):
        # a route whose check the scan read is still reported (rule ownership-check-read) with the class and match it read, never hidden
        rows = hub(SERVICE.replace(UPD, UPD.replace("where: { uid }", "where: { uid, ownerUid: requester.uid }")))
        self.assertEqual([r[:3] for r in rows], [("src/things.controller.ts", 13, "ownership-check-read")]
                         + [("src/things.controller.ts", n, "missing-ownership-check") for n in (19, 25)])
        self.assertIn("class=requester-compare; match=", rows[0][3])

    def test_spread_after_owner_key_stays_a_row(self):
        # known misread: `...dto` after the owner key lets the client overwrite ownerUid, yet the scan reads a check; the route must still be a row
        rows = hub(SERVICE.replace(UPD, UPD.replace("where: { uid }", "where: { uid, ownerUid: requester.uid, ...dto }")))
        self.assertIn(13, [r[1] for r in rows])

if __name__ == "__main__":
    unittest.main()
