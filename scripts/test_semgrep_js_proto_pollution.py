#!/usr/bin/env python3
"""Tests for perun.js.prototype-pollution (CWE-1321) in templates/semgrep-taint/js.yml: a for-in or for-of loop that assigns
`target[key] = ...` with no guard on the key is a finding; a loop that compares the key with "__proto__" or a blocklist
`.includes(key)`, and an assignment outside a loop, stay clean. Fixtures use `// ruleid: <id>` (next line must be a finding) and
`// ok: <id>` (next line must stay clean). Live check needs semgrep and prints SKIP without it. RULES=<dir> checks another copy."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
ID = "perun.js.prototype-pollution"

JS = '''
function mergeUnguarded(target, source) {
  for (const key in source) {
    // ruleid: perun.js.prototype-pollution
    target[key] = source[key];
  }
  return target;
}

function mergeRecursive(target, source) {
  for (const key in source) {
    if (typeof source[key] === "object") {
      // ruleid: perun.js.prototype-pollution
      target[key] = mergeRecursive(target[key] || {}, source[key]);
    }
  }
  return target;
}

function mergeSkipProto(target, source) {
  for (const key in source) {
    if (key === "__proto__") continue;
    // ok: perun.js.prototype-pollution
    target[key] = source[key];
  }
  return target;
}

function mergeOnlyNotProto(target, source) {
  for (const key in source) {
    if (key !== "__proto__") {
      // ok: perun.js.prototype-pollution
      target[key] = source[key];
    }
  }
  return target;
}

function mergeBlocklist(target, source) {
  const bad = ["__proto__", "constructor", "prototype"];
  for (const key in source) {
    if (bad.includes(key)) { continue; }
    // ok: perun.js.prototype-pollution
    target[key] = source[key];
  }
  return target;
}

function mergeKeys(target, source) {
  for (const key of Object.keys(source)) {
    // ruleid: perun.js.prototype-pollution
    target[key] = source[key];
  }
  return target;
}

function mergeKeysSkipProto(target, source) {
  for (const key of Object.keys(source)) {
    if (key === "__proto__") continue;
    // ok: perun.js.prototype-pollution
    target[key] = source[key];
  }
  return target;
}

function mergeHasOwnOnly(target, source) {
  for (const key in source) {
    if (!Object.hasOwn(source, key)) continue;
    // ruleid: perun.js.prototype-pollution
    target[key] = source[key];
  }
  return target;
}

function mergeHasOwnAndProto(target, source) {
  for (const key in source) {
    if (!Object.hasOwn(source, key)) continue;
    if (key === "__proto__" || key === "constructor" || key === "prototype") continue;
    // ok: perun.js.prototype-pollution
    target[key] = source[key];
  }
  return target;
}

function setOnce(target, key, value) {
  // ok: perun.js.prototype-pollution
  target[key] = value;
}
'''


def annotated(body, kind):
    return {i + 2 for i, l in enumerate(body.splitlines()) if re.match(rf"\s*// {kind}: {ID}$", l)}


want, ok = annotated(JS, "ruleid"), annotated(JS, "ok")
assert len(want) == 4 and len(ok) == 6, (want, ok)
rule = open(os.path.join(RULES, "js.yml")).read()
assert f"- id: {ID}" in rule and "for ($K in $S)" in rule

if os.environ.get("REQUIRE_SEMGREP") and not shutil.which("semgrep"):
    raise SystemExit("FAIL: REQUIRE_SEMGREP=1 but semgrep is not installed")
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "app.js"), "w").write(JS)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", "app.js"],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = {x["start"]["line"] for x in r["results"] if x["check_id"].endswith(ID)}
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
    print("semgrep-js-proto-pollution: live ok")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-js-proto-pollution: ok")
