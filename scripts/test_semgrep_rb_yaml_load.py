#!/usr/bin/env python3
"""Tests for perun.rb.yaml-load-params (CWE-502) in templates/semgrep-taint/rb.yml: YAML.load, Psych.load, YAML.unsafe_load or
Psych.unsafe_load of a params[...] value is a finding; safe_load and a literal or file argument stay clean. Fixtures use
`# ruleid: <id>` (next line must be a finding) and `# ok: <id>` (next line must stay clean). Live check needs semgrep and prints
SKIP without it. RULES=<dir> checks another copy."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
ID = "perun.rb.yaml-load-params"

RB = '''
require 'yaml'

def import_load
  # ruleid: perun.rb.yaml-load-params
  YAML.load(params[:data])
end

def import_psych
  # ruleid: perun.rb.yaml-load-params
  Psych.load(params[:data])
end

def import_unsafe
  # ruleid: perun.rb.yaml-load-params
  YAML.unsafe_load(params[:data])
end

def import_safe
  # ok: perun.rb.yaml-load-params
  YAML.safe_load(params[:data], permitted_classes: [Symbol])
end

def import_load_allowlist
  # ok: perun.rb.yaml-load-params
  YAML.load(params[:d], permitted_classes: [Symbol])
end

def load_config_file
  # ok: perun.rb.yaml-load-params
  YAML.load(File.read("config/settings.yml"))
end
'''


def annotated(body, kind):
    return {i + 2 for i, l in enumerate(body.splitlines()) if re.match(rf"\s*# {kind}: {ID}$", l)}


want, ok = annotated(RB, "ruleid"), annotated(RB, "ok")
assert len(want) == 3 and len(ok) == 3, (want, ok)
rule = open(os.path.join(RULES, "rb.yml")).read()
assert f"- id: {ID}" in rule and "YAML.load(params[...], ...)" in rule

if os.environ.get("REQUIRE_SEMGREP") and not shutil.which("semgrep"):
    raise SystemExit("FAIL: REQUIRE_SEMGREP=1 but semgrep is not installed")
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "app.rb"), "w").write(RB)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", "app.rb"],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = {x["start"]["line"] for x in r["results"] if x["check_id"].endswith(ID)}
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
    print("semgrep-rb-yaml-load: live ok")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-rb-yaml-load: ok")
