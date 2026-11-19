"""route_auth_map.py ts-rest support: NestJS members declared with `@Api(server.route.x)`, `@TsRest(contract.x)` or `@TsRestHandler(c.x)`
are one row each, METHOD and path read from the scanned `initContract().router({...})` contract when it is statically findable, else
`ANY contract:<key>`; `@UseGuards(X)` on the member or the class is the evidence. Also the coverage line, which counts the files whose
route-like decorators gave no row. Fixtures are fictional (Acme, example.com)."""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/route_auth_map.py"

CONTRACT = """import { initContract } from '@ts-rest/core';
import { z } from 'zod';
const c = initContract();
const V = '/v1';

export const acmeWidgets = c.router({
  getWidget: { method: 'GET', path: '/v1/widgets/:uid', responses: { 200: c.type<unknown>() } },
  updateWidget: {
    body: z.object({ path: z.string(), method: z.string() }),
    method: 'PUT',
    path: `${V}/widgets/:uid`,
    responses: { 200: c.type<unknown>() },
  },
  deleteWidget: { method: 'DELETE' as const, path: '/v1/widgets/:uid', responses: { 204: c.noBody() } },
  dynamicWidget: { method: 'POST', path: V + '/widgets/dynamic', responses: { 200: c.type<unknown>() } },
  nested: c.router({ inner: { method: 'POST', path: '/v1/inner', responses: { 200: c.type<unknown>() } } }),
});

export const acmeAdmin = c.router({ purge: { method: 'POST', path: '/purge', responses: { 200: c.type<unknown>() } } }, { pathPrefix: '/admin' });
"""
SERVER = """import { Controller, UseGuards } from '@nestjs/common';
import { Api, initNestServer } from '@ts-rest/nest';
import { acmeWidgets } from './contract';
const server = initNestServer(acmeWidgets);

@Controller()
export class WidgetsController {
  @Api(server.route.getWidget)
  get() { return 1; }

  @Api(server.route.updateWidget)
  @UseGuards(AcmeTokenGuard)
  update() { return 1; }

  @UseGuards(AcmeTokenGuard)
  @Api(server.route.deleteWidget)
  remove() { return 1; }

  @Api(server.route.dynamicWidget)
  dynamic() { return 1; }

  @Api(server.route.nested.inner)
  inner() { return 1; }

  @Public()
  @Api(server.route.missingKey)
  missing() { return 1; }
}
"""
HANDLER = """import { Controller, UseGuards } from '@nestjs/common';
import { TsRest, TsRestHandler, nestControllerContract, tsRestHandler } from '@ts-rest/nest';
import { acmeAdmin } from './contract';
import { acmeBilling } from '@acme/contracts';
const h = nestControllerContract(acmeAdmin);

@UseGuards(AcmeAdminGuard)
@TsRest({ jsonQuery: true })
@Controller('ops')
export class OpsController {
  @TsRestHandler(h.purge)
  purge() { return tsRestHandler(h.purge, async () => ({ status: 200, body: 1 })); }

  @TsRest(acmeAdmin.purge)
  purgeAgain() { return 1; }

  @TsRestHandler(acmeAdmin)
  all() { return 1; }
}

@Controller('billing')
export class BillingController {
  @TsRestHandler(acmeBilling.charge)
  charge() { return 1; }
}
"""
DUP_A = "export const acmeDup = c.router({ x: { method: 'GET', path: '/a' } });\n"
DUP_B = "export const acmeDup = c.router({ x: { method: 'POST', path: '/b' } });\n"
DUP_USE = """@Controller()
export class DupController {
  @Api(acmeDup.x)
  x() { return 1; }
}
"""
DUP_ONE_FILE = """export function acmeLegacy() { const acmeTwice = c.router({ x: { method: 'GET', path: '/a' } }); return acmeTwice; }
export function acmeCurrent() { const acmeTwice = c.router({ x: { method: 'POST', path: '/b' } }); return acmeTwice; }
"""
DUP_ONE_USE = """@Controller()
export class TwiceController {
  @Api(acmeTwice.x)
  x() { return 1; }
}
"""
API_ONLY = """export abstract class AcmeApiBase {
  @Api(server.route.ping)
  ping() { return 1; }
}
"""
NO_CONTROLLER = """// A base class with route decorators but no @Controller: Nest never mounts it, and this scan does not read it either.
export abstract class AcmeBase {
  @Get('health')
  health() { return 1; }

  @Api(server.route.ping)
  ping() { return 1; }
}
"""
PLAIN = """@Controller('plain')
export class PlainController {
  @Post('x')
  x() { return 1; }
}
"""


def run(files, flag=None):
    with tempfile.TemporaryDirectory() as d:
        for n, t in files.items():
            (Path(d) / n).parent.mkdir(parents=True, exist_ok=True)
            (Path(d) / n).write_text(t, encoding="utf-8")
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), *([flag] if flag else []), d], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.splitlines(), r.stderr


def lines(files):
    return [l.split(": ", 1)[1] for l in run(files)[0] if re.match(r"\S+:\d+: (?:HIGH|INFO): ", l)]


class TsRestRoutes(unittest.TestCase):
    def test_server_route_resolves_method_and_path_from_the_contract(self):
        out = lines({"src/contract.ts": CONTRACT, "src/widgets.controller.ts": SERVER})
        self.assertIn("INFO: GET /v1/widgets/:uid auth=none", out)
        self.assertIn("INFO: PUT /{?}/widgets/:uid auth=UseGuards(AcmeTokenGuard)", out)  # body schema's own path/method fields ignored
        self.assertIn("INFO: DELETE /v1/widgets/:uid auth=UseGuards(AcmeTokenGuard)", out)  # `as const` read, guard above the decorator
        self.assertIn("HIGH: POST contract:dynamicWidget auth=none", out)  # a concatenated path is not guessed
        self.assertIn("HIGH: ANY contract:nested.inner auth=none", out)  # a nested router is not entered
        self.assertIn("INFO: ANY contract:missingKey auth=public", out)
        self.assertEqual(len(out), 6)

    def test_handler_forms_class_guard_prefix_and_unresolved_contract(self):
        out = lines({"src/contract.ts": CONTRACT, "src/ops.controller.ts": HANDLER})
        self.assertEqual(out.count("INFO: POST /ops/admin/purge auth=UseGuards(AcmeAdminGuard)"), 2)  # nestControllerContract and the contract itself; pathPrefix applied
        self.assertIn("INFO: ANY contract:acmeAdmin auth=UseGuards(AcmeAdminGuard)", out)  # a whole-router handler
        self.assertIn("HIGH: ANY contract:charge auth=none", out)  # contract not in the scanned tree: no guess, not joined to the prefix
        self.assertEqual(len(out), 4)  # the class-level `@TsRest({ jsonQuery })` options are no route

    def test_a_name_defined_twice_is_not_resolved(self):
        out = lines({"a/contract.ts": DUP_A, "b/contract.ts": DUP_B, "c/dup.controller.ts": DUP_USE})
        self.assertEqual(out, ["HIGH: ANY contract:x auth=none"])

    def test_a_name_defined_twice_in_one_file_is_not_resolved(self):
        out = lines({"src/contract.ts": DUP_ONE_FILE, "src/twice.controller.ts": DUP_ONE_USE})
        self.assertEqual(out, ["HIGH: ANY contract:x auth=none"])  # neither definition wins

    def test_a_same_named_contract_from_an_unscanned_package_binds_by_name(self):
        # Pins a known limit: the lookup is by contract name, not by import, so the scanned acmeWidgets answers for the package's.
        out = lines({"vendor-copy/contract.ts": CONTRACT, "src/widgets.controller.ts": SERVER.replace("'./contract'", "'@acme/contracts'")})
        self.assertIn("INFO: GET /v1/widgets/:uid auth=none", out)

    def test_all_lists_resolved_routes(self):
        out = run({"src/contract.ts": CONTRACT, "src/widgets.controller.ts": SERVER}, "--all")[0]
        self.assertTrue(any(re.fullmatch(r"PUT /\{\?\}/widgets/:uid src/widgets\.controller\.ts:\d+", l) for l in out), out)


class Coverage(unittest.TestCase):
    def test_counts_files_whose_route_decorators_gave_no_row(self):
        out, err = run({"src/base.ts": NO_CONTROLLER, "src/plain.controller.ts": PLAIN})
        self.assertIn("coverage: 1 file(s) with route-like decorators this scan skipped src/base.ts:3\n", err)  # plain.controller.ts gave its row
        self.assertIn("src/plain.controller.ts:3: HIGH: POST /plain/x auth=none", out)

    def test_counts_a_file_whose_only_route_decorator_is_ts_rest(self):
        err = run({"src/api_base.ts": API_ONLY})[1]
        self.assertIn("coverage: 1 file(s) with route-like decorators this scan skipped src/api_base.ts:2\n", err)

    def test_zero_when_every_decorator_gave_a_row(self):
        err = run({"src/contract.ts": CONTRACT, "src/widgets.controller.ts": SERVER, "src/plain.controller.ts": PLAIN})[1]
        self.assertIn("coverage: 0 file(s) with route-like decorators this scan skipped\n", err)

    def test_inventory_mode_prints_it_too(self):
        err = run({"src/base.ts": NO_CONTROLLER}, "--all")[1]
        self.assertIn("coverage: 1 file(s)", err)


if __name__ == "__main__":
    unittest.main()
