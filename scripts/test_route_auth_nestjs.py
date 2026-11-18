"""route_auth_map.py NestJS support: `@Controller('prefix')` + `@Get|Post|...('path')` routes, `@UseGuards(X)` on the member or the class as auth evidence,
a repo-wide global guard (`APP_GUARD`, `useGlobalGuards(`) read as `global guard, unverified`. Fixtures are fictional (widgets, example.com)."""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/route_auth_map.py"

CLASS_GUARD = """import { Controller, Get, Post, UseGuards } from '@nestjs/common';

@UseGuards(JwtAuthGuard)
@Controller('widgets')
export class WidgetsController {
  @Get(':id')
  find(@Param('id') id: string) { return id; }

  @Post()
  create(@Body() body: { name: string }) { return body; }
}
"""
METHOD_GUARD = """@Controller('gadgets')
export class GadgetsController {
  @UseGuards(AuthGuard('jwt'))
  @Delete(':id')
  remove(@Param('id') id: string) { return id; }

  @Put(':id')
  @UseGuards(RolesGuard)
  replace(@Param('id') id: string) { return id; }

  @Patch(':id')
  patch(@Param('id') id: string) { return id; }
}
"""
OPEN = """@Controller()
export class OpenController {
  @Post('hook')
  hook(@Body() body: unknown) { return body; }

  @All('any')
  any() { return 1; }
}
"""
PREFIX_EMPTY = """@Controller('/v1/things/')
export class ThingsController {
  @Get()
  list() { return []; }

  @Get('/:id/')
  one() { return 1; }
}
"""
GLOBAL = "providers: [{ provide: APP_GUARD, useClass: JwtAuthGuard }]\n"


def rows(files, flag=None):
    with tempfile.TemporaryDirectory() as d:
        for n, t in files.items():
            (Path(d) / n).parent.mkdir(parents=True, exist_ok=True)
            (Path(d) / n).write_text(t, encoding="utf-8")
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), *([flag] if flag else []), d], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.splitlines()


def lines(files):
    return [l.split(": ", 1)[1] for l in rows(files) if re.match(r"\S+:\d+: (?:HIGH|INFO): ", l)]


THROTTLE_GLOBAL = "providers: [{ provide: APP_GUARD, useClass: ThrottlerGuard }]\n"
THROTTLE_USE = """@Controller('rates')
export class RatesController {
  @UseGuards(ThrottlerGuard)
  @Post()
  a() { return 1; }

  @UseGuards(ThrottlerGuard, JwtAuthGuard)
  @Post('both')
  b() { return 1; }
}
"""
ONE_LINE = """@UseGuards(JwtAuthGuard) @Controller('f1') export class F1 { @Post() a() { return 1; } }
@Controller('f2')
export class F2 {
  @Post()
  b() { return 1; }
}
"""
SHAPES = """@Controller({ path: 'users', version: '1' })
export class UsersController {
  @Post(['x', 'y'])
  two() { return 1; }

  @Post(ROUTE_CONST)
  unknown() { return 1; }

  @Head('h')
  head() { return 1; }

  @Options('o')
  opts() { return 1; }
}
"""
PUBLIC = """@Controller('pub')
export class PubController {
  @Public()
  @Post('login')
  login() { return 1; }

  @Post('save')
  save() { return 1; }
}
"""


RATE_AUTH = """@Controller('lim')
export class LimController {
  @UseGuards(RateLimitedAuthGuard)
  @Post('a')
  a() { return 1; }

  @UseGuards(RateLimitGuard)
  @Post('b')
  b() { return 1; }
}
"""
GLOBAL_REVERSED = "providers: [{ useClass: JwtAuthGuard, provide: APP_GUARD }]\n"
THROTTLE_REVERSED = "providers: [{ useClass: ThrottlerGuard, provide: APP_GUARD }]\n"


MEMBER_PUBLIC = """@UseGuards(JwtAuthGuard)
@Controller('mp')
export class MpController {
  @Public()
  @Post('login')
  login() { return 1; }

  @Post('save')
  save() { return 1; }
}
"""
CLASSNAME = """@Controller('cn')
@Meta({ className: 1 })
@UseGuards(JwtAuthGuard)
export class CnController {
  @Post()
  a() { return 1; }
}
"""
GUARDED_B = "@Controller('b')\nexport class BController {\n  @Post('save')\n  save() { return 1; }\n}\n"
GUARDED_A = GUARDED_B.replace("'b'", "'a'").replace("BController", "AController")
PKG = '{ "name": "app" }\n'


ROOT_PKG_APPS = {"package.json": PKG, "apps/a/src/app.module.ts": GLOBAL, "apps/a/src/a.controller.ts": GUARDED_A, "apps/b/src/b.controller.ts": GUARDED_B}
BODY_PUBLIC = """@Controller('bp')
export class BpController {
  @Post('run')
  run() { return this.svc.run(@Public()); }
}
"""


SPACED = "@Controller('sp')\nexport class SpController {\n  @UseGuards (JwtAuthGuard)\n  @Post('a')\n  a() { return 1; }\n\n  @Post('b')\n  @ApiBody<Foo>({}) @UseGuards(JwtAuthGuard)\n  b() { return 1; }\n}\n"


EXPRESS_SAFE = 'const app = require("express")();\napp.options("/w", (req, res) => res.send("x"));\napp.head("/h", (req, res) => res.send("x"));\napp.post("/save", (req, res) => res.send("x"));\n'
FASTIFY_SAFE = 'const fastify = require("fastify")();\nfastify.head("/h", async () => 1);\nfastify.post("/save", async () => 1);\n'
FWD_A = {"app/api/x/route.ts": 'export async function POST(req: Request) {\n  const h = resolveAuthHeader(req);\n  if (!h) return Response.json({}, { status: 401 });\n  return fetch("https://api.example.com/x", { method: "POST", headers: { authorization: h } });\n}\n'}
FWD_B = {"app/api/x/route.ts": FWD_A["app/api/x/route.ts"].replace("authorization: h", '"x-y": h')}  # same file and line, no forwarded credential
TWOSCAN = """import importlib.util, io, os, sys
from contextlib import redirect_stdout
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("route_auth_map", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for d in sys.argv[2:]:
    out = io.StringIO()
    with redirect_stdout(out): m.main(["x", d])
print(out.getvalue(), end="")
"""


def twoscan(script, *trees):
    """stdout of the LAST of several scans run in one process, so state left by an earlier scan would show."""
    with tempfile.TemporaryDirectory() as d:
        dirs = []
        for i, files in enumerate(trees):
            for n, t in files.items():
                (Path(d) / str(i) / n).parent.mkdir(parents=True, exist_ok=True)
                (Path(d) / str(i) / n).write_text(t, encoding="utf-8")
            dirs.append(str(Path(d) / str(i)))
        r = subprocess.run([sys.executable, "-I", "-c", TWOSCAN, str(script), *dirs], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


class ScanState(unittest.TestCase):
    def test_second_scan_in_one_process_does_not_inherit_the_first_scans_state(self):
        self.assertIn("INFO: POST /api/x auth=presence-check", twoscan(SCRIPT, FWD_A))  # control: forwarded credential is INFO
        self.assertIn("HIGH: POST /api/x auth=presence-check", twoscan(SCRIPT, FWD_A, FWD_B))

    def test_express_and_fastify_head_options_make_no_rows(self):
        self.assertEqual(lines({"e.js": EXPRESS_SAFE}), ["HIGH: POST /save auth=none"])
        self.assertEqual(lines({"f.js": FASTIFY_SAFE}), ["HIGH: POST /save auth=none"])


class NestRoutes(unittest.TestCase):
    def test_guard_decorator_with_space_or_generic_argument_is_read(self):
        self.assertEqual(lines({"s.controller.ts": SPACED}), ["INFO: POST /sp/a auth=UseGuards(JwtAuthGuard)", "INFO: POST /sp/b auth=UseGuards(JwtAuthGuard)"])
        self.assertEqual(lines({"s.controller.ts": SPACED.replace("JwtAuthGuard", "ThrottlerGuard")}), ["HIGH: POST /sp/a auth=none", "HIGH: POST /sp/b auth=none"])  # twin

    def test_root_manifest_only_monorepo_scopes_guard_by_nest_cli_projects(self):
        cli = '{ "projects": { "a": { "root": "apps/a" }, "b": { "root": "apps/b", "sourceRoot": "apps/b/src" } } }'
        want = ["HIGH: POST /b/save auth=none", "INFO: POST /a/save auth=global guard, unverified"]
        self.assertEqual(sorted(lines({**ROOT_PKG_APPS, "nest-cli.json": cli})), want)

    def test_root_manifest_only_monorepo_falls_back_to_main_ts(self):
        f = {**ROOT_PKG_APPS, "apps/a/src/main.ts": "bootstrap();\n", "apps/b/src/main.ts": "bootstrap();\n"}
        self.assertEqual(sorted(lines(f)), ["HIGH: POST /b/save auth=none", "INFO: POST /a/save auth=global guard, unverified"])
        g = {**ROOT_PKG_APPS, "apps/a/tsconfig.app.json": "{}", "apps/b/tsconfig.app.json": "{}"}
        self.assertEqual(sorted(lines(g)), sorted(lines(f)))

    def test_public_call_inside_a_member_body_is_not_a_decorator(self):
        self.assertEqual(lines({"b.controller.ts": BODY_PUBLIC}), ["HIGH: POST /bp/run auth=none"])

    def test_head_options_stay_info_for_nest(self):
        self.assertEqual(lines({"u.controller.ts": SHAPES})[-2:], ["INFO: HEAD /users/h auth=none", "INFO: OPTIONS /users/o auth=none"])

    def test_nested_generic_decorator_argument_keeps_the_guard(self):
        f = {"n.controller.ts": SPACED.replace("@ApiBody<Foo>", "@ApiBody<Foo<Bar>>")}
        self.assertEqual(lines(f)[-1], "INFO: POST /sp/b auth=UseGuards(JwtAuthGuard)")

    def test_member_guard_beats_member_public(self):
        both = MEMBER_PUBLIC.replace("  @Public()\n", "  @Public()\n  @UseGuards(OwnGuard)\n")
        self.assertEqual(lines({"m.controller.ts": both})[0], "INFO: POST /mp/login auth=UseGuards(OwnGuard)")
        self.assertEqual(lines({"m.controller.ts": MEMBER_PUBLIC})[0], "INFO: POST /mp/login auth=public")  # twin: no member guard

    def test_global_guard_without_markers_stays_in_its_src_tree(self):
        f = {"apps/a/src/app.module.ts": GLOBAL, "apps/a/src/a.controller.ts": GUARDED_A, "apps/b/src/b.controller.ts": GUARDED_B}
        self.assertEqual(sorted(lines(f)), ["HIGH: POST /b/save auth=none", "INFO: POST /a/save auth=global guard, unverified"])

    def test_global_guard_reaches_only_its_own_app(self):
        f = {"apps/a/package.json": PKG, "apps/b/package.json": PKG, "apps/a/src/app.module.ts": GLOBAL,
             "apps/a/src/a.controller.ts": GUARDED_A, "apps/b/src/b.controller.ts": GUARDED_B}
        self.assertEqual(sorted(lines(f)), ["HIGH: POST /b/save auth=none", "INFO: POST /a/save auth=global guard, unverified"])
        f["apps/b/src/app.module.ts"] = GLOBAL  # twin: both apps guarded
        self.assertEqual(sorted(lines(f)), ["INFO: POST /a/save auth=global guard, unverified", "INFO: POST /b/save auth=global guard, unverified"])

    def test_member_public_beats_class_guard_and_its_twin_keeps_the_guard(self):
        self.assertEqual(lines({"m.controller.ts": MEMBER_PUBLIC}), ["INFO: POST /mp/login auth=public", "INFO: POST /mp/save auth=UseGuards(JwtAuthGuard)"])

    def test_class_keyword_is_a_word_not_a_substring(self):
        self.assertEqual(lines({"c.controller.ts": CLASSNAME}), ["INFO: POST /cn auth=UseGuards(JwtAuthGuard)"])

    def test_rate_limit_name_with_an_auth_token_still_counts_and_its_twin_does_not(self):
        self.assertEqual(lines({"l.controller.ts": RATE_AUTH}), ["INFO: POST /lim/a auth=UseGuards(RateLimitedAuthGuard)", "HIGH: POST /lim/b auth=none"])

    def test_global_guard_with_provide_after_use_class(self):
        got = lines({"o.controller.ts": OPEN, "app.module.ts": GLOBAL_REVERSED})
        self.assertEqual(got, ["INFO: POST /hook auth=global guard, unverified", "INFO: ANY /any auth=global guard, unverified"])
        self.assertEqual(lines({"o.controller.ts": OPEN, "app.module.ts": THROTTLE_REVERSED}), ["HIGH: POST /hook auth=none", "HIGH: ANY /any auth=none"])

    def test_throttler_only_global_guard_is_not_auth(self):
        self.assertEqual(lines({"o.controller.ts": OPEN, "app.module.ts": THROTTLE_GLOBAL}), ["HIGH: POST /hook auth=none", "HIGH: ANY /any auth=none"])

    def test_throttler_use_guards_is_not_auth_but_a_second_guard_is(self):
        self.assertEqual(lines({"r.controller.ts": THROTTLE_USE}), ["HIGH: POST /rates auth=none", "INFO: POST /rates/both auth=UseGuards(JwtAuthGuard)"])

    def test_class_guard_does_not_leak_into_the_next_class(self):
        self.assertEqual(lines({"f.controller.ts": ONE_LINE}), ["INFO: POST /f1 auth=UseGuards(JwtAuthGuard)", "HIGH: POST /f2 auth=none"])

    def test_options_object_path_array_constant_head_options(self):
        self.assertEqual(lines({"u.controller.ts": SHAPES}), [
            "HIGH: POST /users/x auth=none", "HIGH: POST /users/y auth=none", "HIGH: POST /users/{?} auth=none", "INFO: HEAD /users/h auth=none", "INFO: OPTIONS /users/o auth=none"])

    def test_public_decorator_reads_public_even_under_a_global_guard(self):
        want = ["INFO: POST /pub/login auth=public", "INFO: POST /pub/save auth=global guard, unverified"]
        self.assertEqual(lines({"p.controller.ts": PUBLIC, "app.module.ts": GLOBAL}), want)
        self.assertEqual(lines({"p.controller.ts": PUBLIC}), ["INFO: POST /pub/login auth=public", "HIGH: POST /pub/save auth=none"])

    def test_class_guard_covers_every_member(self):
        self.assertEqual(lines({"w.controller.ts": CLASS_GUARD}), ["INFO: GET /widgets/:id auth=UseGuards(JwtAuthGuard)", "INFO: POST /widgets auth=UseGuards(JwtAuthGuard)"])

    def test_method_guard_covers_only_its_member_above_or_below_the_verb(self):
        self.assertEqual(sorted(lines({"g.controller.ts": METHOD_GUARD})), [
            "HIGH: PATCH /gadgets/:id auth=none", "INFO: DELETE /gadgets/:id auth=UseGuards(AuthGuard)", "INFO: PUT /gadgets/:id auth=UseGuards(RolesGuard)"])

    def test_unguarded_mutation_is_high_and_all_is_any(self):
        self.assertEqual(lines({"o.controller.ts": OPEN}), ["HIGH: POST /hook auth=none", "HIGH: ANY /any auth=none"])

    def test_prefix_with_empty_path_and_slashes(self):
        self.assertEqual(lines({"t.controller.ts": PREFIX_EMPTY}), ["INFO: GET /v1/things auth=none", "INFO: GET /v1/things/:id auth=none"])

    def test_global_guard_is_noted_unverified_not_high(self):
        got = lines({"o.controller.ts": OPEN, "app.module.ts": GLOBAL})
        self.assertEqual(got, ["INFO: POST /hook auth=global guard, unverified", "INFO: ANY /any auth=global guard, unverified"])
        g2 = lines({"o.controller.ts": OPEN, "main.ts": "app.useGlobalGuards(new JwtAuthGuard());\n"})
        self.assertEqual(g2, got)

    def test_explicit_guard_beats_global_note(self):
        got = lines({"w.controller.ts": CLASS_GUARD, "app.module.ts": GLOBAL})
        self.assertEqual(len(got), 2)
        self.assertTrue(all("auth=UseGuards(JwtAuthGuard)" in l for l in got))

    def test_all_flag_lists_prefixed_routes(self):
        self.assertEqual([l.rsplit(":", 1)[0] for l in rows({"t.controller.ts": PREFIX_EMPTY}, "--all")],
                         ["GET /v1/things t.controller.ts", "GET /v1/things/:id t.controller.ts"])


if __name__ == "__main__":
    unittest.main()
