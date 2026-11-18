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


class NestRoutes(unittest.TestCase):
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
