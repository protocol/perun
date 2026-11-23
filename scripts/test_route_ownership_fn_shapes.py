"""Regression tests for route_auth_map.py --privileged ownership rows on shapes that used to print nothing.

Each case failed on the previous head: a Knex `.del()` or CQRS `commandBus.execute(` write, a service call whose body the scan cannot read (an inherited base-class method, a generic
class whose type has braces, a decorator on the method's line), an unresolved ts-rest contract that reads
a path parameter, a member with a privileged path and a plain one, a file name with a tab, and a controller
the scan could not read (now a NOT-CHECKED row, also in review_checks.sh). Fixtures are fictional (Acme)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_route_ownership import CONTROLLER, RC, SCRIPT, SERVICE, TSR_CONTROLLER, TSR_SERVICE, UPD  # noqa: E402

CTL, SVC = "src/things/things.controller.ts", "src/things/things.service.ts"
REMOVE = "    await this.prisma.thing.delete({ where: { uid } });\n"
CREATE_MEMBER = "    return this.things.create(dto, req.user);\n"
OWNER_MEMBER = "    return this.things.create({ title: dto.title, ownerUid: dto.ownerUid }, req.user);\n"


def run(files, *flags):
    """stdout lines of route_auth_map.py [flags] over files {relative path: text}."""
    with tempfile.TemporaryDirectory() as d:
        for rel, text in files.items():
            (Path(d) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(d) / rel).write_text(text)
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *flags, d], capture_output=True, text=True, check=True).stdout.splitlines()


def rows(files, kind="OWN"):
    """Sorted (file, METHOD, route) of the --privileged rows of the given kind (OWN, OWN-CHECKED, PRIV, NOT-CHECKED)."""
    out = []
    for line in run(files, "--privileged"):
        f, _, rest = line.split(":", 2)
        w = rest.split()
        if w[0] == kind + ":": out.append((f, *w[1:3]))
    return sorted(out)


def methods(service=SERVICE, controller=CONTROLLER):
    """Sorted METHODs of the OWN rows for the things fixture."""
    return sorted(r[1] for r in rows({CTL: controller, SVC: service}))


class WriteNames(unittest.TestCase):
    def test_knex_del_and_cqrs_command_are_writes(self):
        # a CQRS command and a Knex delete by id are writes
        svc = SERVICE.replace(UPD, "    return this.commandBus.execute(new RenameThing(uid, dto.title));\n").replace(REMOVE, "    await this.knex('thing').where({ uid }).del();\n")
        self.assertEqual(methods(svc), ["DELETE", "POST", "PUT"])

    def test_names_like_them_are_no_writes(self):
        # another bus's execute and a name that only starts with del write nothing
        for call in ("this.queryBus.execute(new GetThing(uid))", "this.timer.delay(uid)", "this.jobs.delegate(uid)"):
            with self.subTest(call): self.assertEqual(methods(SERVICE.replace(UPD, "    return %s;\n" % call)), ["DELETE", "POST"])


class UnreadServiceCallIsTheWrite(unittest.TestCase):
    def test_service_body_not_read(self):
        # the member's own `this.things.create(` is the write when the scan cannot read the service method
        ctl = CONTROLLER.replace(CREATE_MEMBER, OWNER_MEMBER)
        for name, svc in (
                ("inherited base", "@Injectable()\nexport class ThingsService extends AcmeCrudService<Thing> {\n  constructor(prisma: PrismaService) { super(prisma); }\n}\n"),
                ("generic with braces", SERVICE.replace("export class ThingsService {", "export class ThingsService<T extends { uid: string }> {")),
                ("decorator on the line", SERVICE.replace("  create(dto: CreateThingDto", "  @Transactional() create(dto: CreateThingDto"))):
            with self.subTest(name): self.assertIn("POST", methods(svc, ctl))

    def test_read_service_call_is_no_write(self):
        # a service method that was read and writes nothing still makes no row
        ctl = CONTROLLER.replace(CREATE_MEMBER, OWNER_MEMBER)
        svc = SERVICE.replace("    return this.prisma.thing.create({ data: { title: dto.title, owner: { connect: { uid: dto.ownerUid } } } });\n", "    return this.queue.enqueue(dto);\n")
        self.assertNotEqual(svc, SERVICE)
        self.assertNotIn("POST", methods(svc, ctl))


class UnresolvedTsRest(unittest.TestCase):
    FILES = {"src/widgets/widgets.controller.ts": TSR_CONTROLLER, "src/widgets/widgets.service.ts": TSR_SERVICE}

    def test_unresolved_contract_by_id(self):
        # no contract file: the route is `contract:updateWidget`, and the member reads `params.uid`
        self.assertEqual(rows(self.FILES), [("src/widgets/widgets.controller.ts", "ANY", "contract:updateWidget")])

    def test_unresolved_contract_destructured_param(self):
        ctl = TSR_CONTROLLER.replace("{ params, body }", "{ params: { uid }, body }").replace("params.uid", "uid")
        self.assertEqual(len(rows(dict(self.FILES, **{"src/widgets/widgets.controller.ts": ctl}))), 1)

    def test_unresolved_contract_without_a_param_or_a_write(self):
        # no path parameter read, or (method unknown) no write call: no row
        no_param = TSR_CONTROLLER.replace("params.uid", "body.uid")
        no_write = TSR_SERVICE.replace("this.prisma.widget.update(", "this.prisma.widget.findFirst(")
        # `params.uid` only in a string, or `params` an outbound call's query object: no client id read
        in_string = no_param.replace("    return", "    this.log('reads params.uid');\n    return")
        outbound = no_param.replace("    return", "    await this.http.get('/x', { params: { page: 1 } });\n    return")
        for name, ctl, svc in (("no param", no_param, TSR_SERVICE), ("no write", TSR_CONTROLLER, no_write),
                               ("param in a string", in_string, TSR_SERVICE), ("outbound params", outbound, TSR_SERVICE)):
            with self.subTest(name): self.assertEqual(rows({"src/widgets/widgets.controller.ts": ctl, "src/widgets/widgets.service.ts": svc}), [])


class Dedup(unittest.TestCase):
    def test_priv_path_does_not_hide_the_members_other_path(self):
        files = {CTL: CONTROLLER.replace("@Put(':uid')", "@Put(['users/:uid', ':uid'])"), SVC: SERVICE}
        self.assertEqual(rows(files, "PRIV"), [(CTL, "PUT", "/things/users/:uid")])
        self.assertIn((CTL, "PUT", "/things/:uid"), rows(files))
        self.assertNotIn((CTL, "PUT", "/things/users/:uid"), rows(files))


class OneRowPerLine(unittest.TestCase):
    def test_tab_in_file_name(self):
        # a tab would split the row where review_checks.sh reads it; it prints as `?`
        files = {"src/things/things\tx.controller.ts": CONTROLLER, SVC: SERVICE}
        for flags in ((), ("--privileged",)):
            with self.subTest(flags=flags):
                out = [x for x in run(files, *flags) if x.startswith("src/things/things")]
                self.assertTrue(out)
                self.assertFalse([x for x in out if "\t" in x])
                self.assertTrue(all(x.startswith("src/things/things?x.controller.ts:") for x in out))


BASE = "export abstract class AcmeCrudController {\n  @Put(':uid')\n  update(@Param('uid') uid: string) { return this.repo.update(uid); }\n}\n"


class SkippedController(unittest.TestCase):
    def test_not_checked_row(self):
        self.assertEqual(rows({"src/crud.controller.ts": BASE, CTL: CONTROLLER, SVC: SERVICE}, "NOT-CHECKED")[0][0], "src/crud.controller.ts")

    def test_read_controller_is_no_not_checked_row(self):
        self.assertEqual(rows({CTL: CONTROLLER, SVC: SERVICE}, "NOT-CHECKED"), [])

    def test_review_checks_not_checked_row(self):
        env = dict(os.environ, PATH="/usr/bin:/bin")
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "src").mkdir()
            (Path(d) / "src/crud.controller.ts").write_text(BASE)
            for a in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@example.com", "-c", "user.name=Acme", "commit", "-qm", "fixture"]):
                subprocess.run(["git", "-C", d, *a], check=True, capture_output=True, env=env)
            r = subprocess.run(["bash", str(RC), "--full", "--repo", d], capture_output=True, text=True, env=env)
        got = [(x["file"], x["line"], x["rule"]) for x in json.loads(r.stdout) if x["tool"] == "privileged-route"]
        self.assertEqual(got, [("src/crud.controller.ts", 2, "not-checked")])


if __name__ == "__main__":
    unittest.main()
