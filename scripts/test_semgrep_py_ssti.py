#!/usr/bin/env python3
"""Tests for perun.py.ssti (CWE-1336) in templates/semgrep-taint/py.yml: request data or a function parameter compiled as a
template (jinja2.Template, Template, Environment.from_string, render_template_string) is a finding; a literal template with the data
passed as render context stays clean. Fixtures use `# ruleid: <id>` (next line must be a finding) and `# ok: <id>` (next line must
stay clean). Live check needs semgrep and prints SKIP without it. Fictional names only. RULES=<dir> checks another copy."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
ID = "perun.py.ssti"

PY = '''
import flask
import jinja2
import jinja2 as j
from flask import render_template_string, request
from jinja2 import Environment, Template
from jinja2 import Template as T

def ssti_template():
    # ruleid: perun.py.ssti
    return Template(request.args["tpl"]).render()

def ssti_module_template():
    # ruleid: perun.py.ssti
    return jinja2.Template(request.form.get("tpl")).render()

def ssti_from_string():
    # ruleid: perun.py.ssti
    return Environment().from_string(request.args["tpl"]).render()

def ssti_render_string():
    # ruleid: perun.py.ssti
    return render_template_string(request.args["tpl"])

def ssti_param(tpl):
    # ruleid: perun.py.ssti
    return Template(tpl).render()

def ssti_alias_from_import():
    # ruleid: perun.py.ssti
    return T(request.args["tpl"]).render()

def ssti_alias_module():
    # ruleid: perun.py.ssti
    return j.Template(request.args["tpl"]).render()

def ssti_flask_module_render():
    # ruleid: perun.py.ssti
    return flask.render_template_string(request.args["tpl"])

def ssti_get_json():
    # ruleid: perun.py.ssti
    return Template(request.get_json()["tpl"]).render()

def ssti_request_json_attr():
    # ruleid: perun.py.ssti
    return Template(request.json["tpl"]).render()

def ssti_flask_request_get_json_get():
    # ruleid: perun.py.ssti
    return Template(flask.request.get_json().get("tpl")).render()

def clean_literal():
    ctx = {"name": request.args["name"]}
    # ok: perun.py.ssti
    return Template("Hello {{ name }}").render(ctx)

def clean_render_string():
    # ok: perun.py.ssti
    return render_template_string("Hello {{ name }}", name=request.args["name"])
'''


def annotated(body, kind):
    return {i + 2 for i, l in enumerate(body.splitlines()) if re.match(rf"\s*# {kind}: {ID}$", l)}


want, ok = annotated(PY, "ruleid"), annotated(PY, "ok")
assert len(want) == 11 and len(ok) == 2, (want, ok)
rule = open(os.path.join(RULES, "py.yml")).read()
assert f"- id: {ID}" in rule and "render_template_string($S" in rule and "$E.from_string($S" in rule

if os.environ.get("REQUIRE_SEMGREP") and not shutil.which("semgrep"):
    raise SystemExit("FAIL: REQUIRE_SEMGREP=1 but semgrep is not installed")
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "app.py"), "w").write(PY)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", "app.py"],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = {x["start"]["line"] for x in r["results"] if x["check_id"].endswith(ID)}
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
    print("semgrep-py-ssti: live ok")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-py-ssti: ok")
