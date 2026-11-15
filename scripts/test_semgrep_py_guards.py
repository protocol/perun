#!/usr/bin/env python3
"""Tests for bundled semgrep rules in templates/semgrep-taint/py.yml: perun.py.ssrf allowlist guard with abort, perun.py.open-redirect
relative-path guard and url_has_allowed_host_and_scheme, and perun.py.xxe-lxml (CWE-611).

Fixtures are annotated like semgrep's own tests: `# ruleid: <id>` marks the NEXT line as a required finding, `# ok: <id>` the next line
as one that must stay clean; unannotated lines must stay clean. Fictional names only. RULES=<dir> checks another copy. The live check
needs semgrep and prints SKIP without it; the offline pins always run. Plain asserts."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")

PY = '''
import requests
from flask import abort, redirect, request
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from lxml import etree

def ssrf_open():
    # ruleid: perun.py.ssrf
    return requests.get(request.args["url"]).text

def ssrf_guarded(ALLOWED):
    url = request.args["url"]
    if url not in ALLOWED:
        abort(400)
    # ok: perun.py.ssrf
    return requests.get(url).text

def redirect_open():
    # ruleid: perun.py.open-redirect
    return redirect(request.args.get("next", "/"))

def redirect_unguarded():
    nxt = request.args.get("next", "/")
    if nxt.startswith("/"):
        nxt = nxt
    # ruleid: perun.py.open-redirect
    return redirect(nxt)

def redirect_guarded():
    nxt = request.args.get("next", "/")
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = "/"
    # ok: perun.py.open-redirect
    return redirect(nxt)

def redirect_django_guarded():
    nxt = request.GET.get("next", "/")
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts=None):
        nxt = "/"
    # ok: perun.py.open-redirect
    return HttpResponseRedirect(nxt)

def redirect_django_return():
    nxt = request.GET.get("next", "/")
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts=None):
        return "bad"
    # ok: perun.py.open-redirect
    return redirect(nxt)

def xxe_entities():
    # ruleid: perun.py.xxe-lxml
    p = etree.XMLParser(resolve_entities=True)
    return p

def xxe_network():
    # ruleid: perun.py.xxe-lxml
    return etree.XMLParser(no_network=False)

def xxe_both(path):
    # ruleid: perun.py.xxe-lxml
    p = etree.XMLParser(resolve_entities=True, no_network=False)
    return etree.parse(path, p)

def xxe_safe():
    # ok: perun.py.xxe-lxml
    return etree.XMLParser(resolve_entities=False, no_network=True)
'''
IDS = ("perun.py.ssrf", "perun.py.open-redirect", "perun.py.xxe-lxml")


def annotated(body, kind):
    """Return {(rule id, line of the annotated NEXT line)} for `# ruleid:`/`# ok:` comments."""
    out = set()
    for i, l in enumerate(body.splitlines()):
        m = re.match(rf"\s*# {kind}: (\S+)$", l)
        if m:
            out.add((m.group(1), i + 2))
    return out


want, ok = annotated(PY, "ruleid"), annotated(PY, "ok")
assert {i for i, _ in want | ok} == set(IDS) and len(want) == 6 and len(ok) == 5, (len(want), len(ok))

rule = open(os.path.join(RULES, "py.yml")).read()
assert "- id: perun.py.xxe-lxml" in rule and "resolve_entities=True" in rule and "no_network=False" in rule
assert "abort(...)" in rule and "url_has_allowed_host_and_scheme($G" in rule and '$G.startswith("//")' in rule

if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "app.py"), "w").write(PY)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", "app.py"],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = {(x["check_id"].rsplit(".py.", 1)[-1] and "perun.py." + x["check_id"].rsplit(".py.", 1)[-1], x["start"]["line"])
           for x in r["results"] if x["check_id"].rsplit(".py.", 1)[-1] in {i[len("perun.py."):] for i in IDS}}
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
    print("semgrep-py-guards: live ok")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-py-guards: ok")
