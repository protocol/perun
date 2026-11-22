#!/usr/bin/env python3
"""Tests for the exposed debug/management surface rules in templates/semgrep-taint/inventory.yml (OWASP API9:2023).

Each rule has seeded bad fixtures marked `ruleid: <id>` on the line before and a clean twin (an environment-gated setup) that must stay
silent: recall 100%, zero hits on the twins and on test paths. The live check needs semgrep and prints SKIP without it. All names are fictional."""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint", "inventory.yml")
src = open(CFG).read()
IDS = [l.split("id: ")[1] for l in src.splitlines() if l.startswith("- id: ")]
assert len(IDS) == 7 and src.count("    cwe: ") == 7, IDS
# security_verify.py maps WARNING to medium and INFO to low: docs/schema exposure is low, live debug surfaces are medium
SEV = {"perun.js.swagger-ui-ungated": "INFO", "perun.js.graphql-introspection-playground": "INFO",
       "perun.py.flasgger-swagger-ungated": "INFO", "perun.js.status-monitor-ungated": "WARNING", "perun.py.debug-toolbar-urls-ungated": "WARNING",
       "perun.yaml.actuator-expose-all": "WARNING", "perun.generic.actuator-expose-all": "WARNING"}
got_sev = dict(re.findall(r"^- id: (\S+)\n(?:  .*\n)*?  severity: (\w+)", src, re.M))
assert got_sev == SEV, f"severity drift: {got_sev}"

BAD_JS = '''import { NestFactory } from "@nestjs/core";
import { SwaggerModule } from "@nestjs/swagger";
import swaggerUi from "swagger-ui-express";
import statusMonitor from "express-status-monitor";
async function boot(app, doc, server) {
  // ruleid: perun.js.swagger-ui-ungated
  SwaggerModule.setup("docs", app, doc);
  // ruleid: perun.js.swagger-ui-ungated
  server.use("/api-docs", swaggerUi.serve, swaggerUi.setup(doc));
  // ruleid: perun.js.status-monitor-ungated
  server.use(statusMonitor());
  // ruleid: perun.js.status-monitor-ungated
  server.use(require("express-status-monitor")({ path: "/health-ui" }));
  // ruleid: perun.js.graphql-introspection-playground
  const a = new ApolloServer({ typeDefs, resolvers, introspection: true });
  // ruleid: perun.js.graphql-introspection-playground
  const b = new ApolloServer({ typeDefs, resolvers, playground: true });
  // ruleid: perun.js.graphql-introspection-playground
  const c = graphqlHTTP({ schema, graphiql: true });
  if (process.env.NODE_ENV === "production") {
    // ruleid: perun.js.swagger-ui-ungated
    SwaggerModule.setup("docs", app, doc);
  }
}
'''
CLEAN_JS = '''import { SwaggerModule } from "@nestjs/swagger";
import swaggerUi from "swagger-ui-express";
import statusMonitor from "express-status-monitor";
async function boot(app, doc, server) {
  if (process.env.NODE_ENV !== "production") {
    SwaggerModule.setup("docs", app, doc);
    server.use("/api-docs", swaggerUi.serve, swaggerUi.setup(doc));
    server.use(statusMonitor());
  }
  if (process.env.ACME_ENABLE_MONITOR === "1") {
    server.use(require("express-status-monitor")({ path: "/health-ui" }));
  }
  const a = new ApolloServer({ typeDefs, resolvers, introspection: process.env.NODE_ENV !== "production" });
  const b = new ApolloServer({ typeDefs, resolvers, introspection: false, playground: false });
  const c = graphqlHTTP({ schema, graphiql: false });
  const other = express();
  other.use(helmet());
}
'''
BAD_PY = '''from django.urls import include, path
import debug_toolbar
urlpatterns = [
    # ruleid: perun.py.debug-toolbar-urls-ungated
    path("__debug__/", include(debug_toolbar.urls)),
    # ruleid: perun.py.debug-toolbar-urls-ungated
    path("__debug__/", include("debug_toolbar.urls")),
]
# ruleid: perun.py.debug-toolbar-urls-ungated
urlpatterns += debug_toolbar_urls()
if not settings.DEBUG:
    # ruleid: perun.py.debug-toolbar-urls-ungated
    urlpatterns += debug_toolbar_urls()
'''
CLEAN_PY = '''from django.conf import settings
from django.urls import include, path
import debug_toolbar
urlpatterns = [path("orders/", include("orders.urls"))]
if settings.DEBUG:
    urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
    urlpatterns += debug_toolbar_urls()
'''
BAD_PY_DOCS = '''from flasgger import Swagger
# ruleid: perun.py.flasgger-swagger-ungated
Swagger(flask_app)
'''
CLEAN_PY_DOCS = '''import os
from flasgger import Swagger
if settings.DEBUG:
    Swagger(flask_app)
if os.environ.get("ENV") != "production":
    Swagger(flask_app)
'''
CLEAN_PY_OTHER = '''class Swagger:
    pass
Swagger(app)
class FastAPIClient:
    pass
FastAPIClient()
'''
BAD_YML = '''# ruleid: perun.yaml.actuator-expose-all
management:
  endpoints:
    web:
      exposure:
        include: "*"
'''
BAD_YML_Q = '''# ruleid: perun.yaml.actuator-expose-all
management:
  endpoints:
    web:
      exposure:
        include: '*'
'''
BAD_YML_LIST = BAD_YML.replace('"*"', '["*"]')
BAD_YML_LIST_Q = BAD_YML.replace('"*"', "['*']")
BAD_YML_FLAT_Q = '''# ruleid: perun.yaml.actuator-expose-all
management.endpoints.web.exposure.include: '*'
'''
BAD_YML_FLAT_LIST = '''# ruleid: perun.yaml.actuator-expose-all
management.endpoints.web.exposure.include: ["*"]
'''
BAD_YML_FLAT = '''# ruleid: perun.yaml.actuator-expose-all
management.endpoints.web.exposure.include: "*"
'''
CLEAN_YML = '''management:
  endpoints:
    web:
      exposure:
        include: "health,info"
'''
BAD_PROPS = '''# ruleid: perun.generic.actuator-expose-all
management.endpoints.web.exposure.include=*
'''
CLEAN_PROPS = '''management.endpoints.web.exposure.include=health,info
# management.endpoints.web.exposure.include=*
'''
BAD = {"app/bad_docs.py": BAD_PY_DOCS, "app/bad.js": BAD_JS,"app/bad.ts": BAD_JS, "app/bad.py": BAD_PY, "app/application.yml": BAD_YML,
       "app/application-prod.yaml": BAD_YML_FLAT, "app/a1.yml": BAD_YML_Q, "app/a2.yml": BAD_YML_LIST,
       "app/a3.yml": BAD_YML_LIST_Q, "app/a4.yml": BAD_YML_FLAT_Q, "app/a5.yml": BAD_YML_FLAT_LIST,"app/application.properties": BAD_PROPS}
CLEAN = {"app/clean_docs.py": CLEAN_PY_DOCS, "app/clean_other.py": CLEAN_PY_OTHER, "app/clean.js": CLEAN_JS,"app/clean.ts": CLEAN_JS, "app/clean.py": CLEAN_PY, "app/application.yml": CLEAN_YML,
         "app/application.properties": CLEAN_PROPS,
         # a dev/local profile file is the environment gate for config
         "app/application-dev.yml": BAD_YML, "app/application-local.properties": BAD_PROPS}
SKIPPED = {"tests/bad.py": BAD_PY, "app/bad.spec.ts": BAD_JS}

if not shutil.which("semgrep"):
    if os.environ.get("REQUIRE_SEMGREP") == "1":
        print("FAIL: semgrep not installed but REQUIRE_SEMGREP=1; the live fixture check cannot run")
        sys.exit(1)
    print("SKIP: semgrep not installed; the live fixture check did not run")
    sys.exit(0)
d = tempfile.mkdtemp()
try:
    want = set()
    # bad and clean twins share file names (application.yml): write them to separate dirs
    for tag, files in (("bad", BAD), ("clean", CLEAN), ("skipped", SKIPPED)):
        for rel, text in files.items():
            p = os.path.join(d, tag, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w").write(text)
    for rel, text in BAD.items():
        lines = text.splitlines()
        want |= {(f"bad/{rel}", i + 2, l.split("ruleid: ")[1]) for i, l in enumerate(lines) if "ruleid: " in l}
    run = subprocess.run(["semgrep", "--config", CFG, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", "."],
                         cwd=d, capture_output=True, text=True)
    out = json.loads(run.stdout)
    got = {(r["path"], r["start"]["line"], re.search(r"perun\.(?:py|js|yaml|generic)\..*$", r["check_id"])[0]) for r in out["results"]}
    assert got == want, f"missing {sorted(want - got)} extra {sorted(got - want)}"
    ids = {i for _, _, i in got}
    assert ids == set(IDS), f"rules without a bad fixture: {set(IDS) - ids}"
finally:
    shutil.rmtree(d)
print(f"ok: {len(want)} bad findings, 0 on clean twins and test paths")
