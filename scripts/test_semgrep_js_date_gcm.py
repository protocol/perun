#!/usr/bin/env python3
"""Tests for the bundled semgrep rules perun.js.date-parse-rollover and perun.js.gcm-no-auth-tag-length (js.yml).

Fixtures are annotated like semgrep's own tests: a `// ruleid: <id>` comment marks the NEXT line as a required finding, an
`// ok: <id>` comment marks the next line as one that must stay clean, and every unannotated line must stay clean too
(so must a copy of the date fixture under a test path). All fixture names and values are fictional. RULES=<file|dir> checks another copy of the rules (used to show the cases fail
without them). The live check needs semgrep and prints SKIP without it (CI installs none); the offline checks always run.
Plain asserts."""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
DATE, GCM = "perun.js.date-parse-rollover", "perun.js.gcm-no-auth-tag-length"

DATES = r'''
// ruleid: perun.js.date-parse-rollover
const isDay = (s) => /^\d{4}-\d{2}-\d{2}$/.test(s) && Number.isFinite(Date.parse(`${s}T00:00:00Z`));
// ruleid: perun.js.date-parse-rollover
const notNaN = (s) => !Number.isNaN(Date.parse(s));
// ruleid: perun.js.date-parse-rollover
const legacy = (s) => !isNaN(Date.parse(s));
// ruleid: perun.js.date-parse-rollover
const viaDate = (s) => !isNaN(new Date(s));
// ruleid: perun.js.date-parse-rollover
const viaTime = (s) => !Number.isNaN(new Date(s).getTime());
// A check on a variable bound first stays unflagged: those hits were mostly display, age and TTL helpers.
function boundDate(s) {
  const d = new Date(s);
  // ok: perun.js.date-parse-rollover
  if (isNaN(d.getTime())) throw new Error("bad date");
  return d;
}
function boundMs(s) {
  const ms = Date.parse(s);
  // ok: perun.js.date-parse-rollover
  if (!Number.isFinite(ms)) return null;
  return ms;
}
class Form {
  validate(s) {
    // ruleid: perun.js.date-parse-rollover
    return Number.isFinite(Date.parse(s));
  }
}
// ok: perun.js.date-parse-rollover
const roundTrip = (s) => Number.isFinite(Date.parse(s)) && new Date(s).toISOString().slice(0, 10) === s;
function realDay(s) {
  const ms = /^\d{4}-\d{2}-\d{2}$/.test(s) ? Date.parse(`${s}T00:00:00Z`) : NaN;
  // ok: perun.js.date-parse-rollover
  return Number.isFinite(ms) && new Date(ms).toISOString().slice(0, 10) === s;
}
function boundRoundTrip(s) {
  const d = new Date(s);
  // ok: perun.js.date-parse-rollover
  if (Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== s) throw new Error("bad date");
  return d;
}
function twoSteps(s) {
  // ok: perun.js.date-parse-rollover
  if (!Number.isFinite(Date.parse(s))) return false;
  return new Date(s).toISOString().startsWith(s);
}
function addDay(s) {
  // ok: perun.js.date-parse-rollover
  return new Date(Date.parse(s) + 86400000);
}
'''

GCM_JS = r'''
const crypto = require("node:crypto");
const { createDecipheriv } = crypto;
const ALGO = "aes-256-gcm";
const TAG_BYTES = 16;
// ruleid: perun.js.gcm-no-auth-tag-length
const a = crypto.createDecipheriv("aes-256-gcm", key, iv);
// ruleid: perun.js.gcm-no-auth-tag-length
const b = createDecipheriv("aes-128-gcm", key, iv);
// ruleid: perun.js.gcm-no-auth-tag-length
const c = crypto.createDecipheriv(ALGO, key, iv);
// ruleid: perun.js.gcm-no-auth-tag-length
const d = crypto.createDecipheriv("AES-256-GCM", key, iv);
// ruleid: perun.js.gcm-no-auth-tag-length
const e = crypto.createDecipheriv("id-aes256-GCM", key, iv);
// ruleid: perun.js.gcm-no-auth-tag-length
const f = crypto.createDecipheriv("aes-256-gcm", key, iv, {});
// ruleid: perun.js.gcm-no-auth-tag-length
const g = createDecipheriv("aes-256-gcm", key, iv, { highWaterMark: 4096 });
// ruleid: perun.js.gcm-no-auth-tag-length
const h = require("node:crypto").createDecipheriv("aes-256-gcm", key, iv);
// ok: perun.js.gcm-no-auth-tag-length
const i = crypto.createDecipheriv("aes-256-gcm", key, iv, { authTagLength: 16 });
// ok: perun.js.gcm-no-auth-tag-length
const j = createDecipheriv("aes-128-gcm", key, iv, { authTagLength: 16 });
// ok: perun.js.gcm-no-auth-tag-length
const k = crypto.createDecipheriv(ALGO, key, iv, { authTagLength: TAG_BYTES });
// ok: perun.js.gcm-no-auth-tag-length
const l = crypto.createDecipheriv("aes-256-gcm", key, iv, { authTagLength });
// ok: perun.js.gcm-no-auth-tag-length
const m = crypto.createDecipheriv("aes-256-gcm", key, iv, { ...opts, authTagLength: 16 });
// ok: perun.js.gcm-no-auth-tag-length
const n = crypto.createDecipheriv("aes-256-cbc", key, iv);
// ok: perun.js.gcm-no-auth-tag-length
const o = crypto.createCipheriv("aes-256-gcm", key, iv);
// ok: perun.js.gcm-no-auth-tag-length
const p = crypto.createDecipheriv("aes-256-gcm", key, iv, opts);
// ok: perun.js.gcm-no-auth-tag-length
const q = crypto.createDecipheriv(pickCipher(kind), key, iv);
'''

FILES = {"app/dates.js": DATES, "app/dates.ts": DATES, "app/gcm.js": GCM_JS, "app/gcm.ts": GCM_JS}
SKIPPED = {"tests/dates.test.js": DATES}  # test paths are excluded from the date rule: nothing in this copy may be reported
ANN =re.compile(r"^\s*//\s*(ruleid|ok):\s*(\S+)\s*$")


def annotated(body, kind):
    """(line, rule id) of the line each `// <kind>: <id>` comment points at (the next one); the id must be one of ours."""
    out = {(i + 1, m.group(2)) for i, l in enumerate(body.split("\n"), 1) if (m := ANN.match(l)) and m.group(1) == kind}
    assert {r for _, r in out} <= {DATE, GCM}, out
    return out


assert all(annotated(b, "ok") and annotated(b, "ruleid") for b in FILES.values())  # both kinds present in every fixture
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for p, body in {**FILES, **SKIPPED}.items():
            os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
            open(os.path.join(d, p), "w").write(body)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", *FILES, *SKIPPED],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = set()  # semgrep prefixes a rule id with each local config's directory: keep the perun.js.<name> tail
    for x in r["results"]:
        rid = "perun.js." + x["check_id"].rsplit("perun.js.", 1)[-1]
        if rid in (DATE, GCM):
            got.add((x["path"], x["start"]["line"], rid))
    want = {(p, ln, rid) for p, body in FILES.items() for ln, rid in annotated(body, "ruleid")}
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
else:
    print("SKIP: semgrep not installed; the live fixture check did not run, the offline checks below do")

# Offline: severities, the fix named in each message, the cipher regex (semgrep anchors metavariable-regex at the start, so
# a bare `gcm$` matches nothing; Python's re.match anchors the same way) and structural pins on the rule text. CI installs no
# semgrep, so every guard the live fixtures prove (round-trip suppression, test-path skip, authTagLength exemption, no
# variable-bound forms) is pinned here too: dropping one fails this file even when the live part is skipped.
SRC = open(RULES if os.path.isfile(RULES) else os.path.join(RULES, "js.yml")).read()
block = lambda rid: SRC.split(f"- id: {rid}\n")[1].split("\n- id:")[0]
assert "  severity: INFO\n" in block(DATE) and "toISOString" in block(DATE)
assert "  severity: WARNING\n" in block(GCM) and "authTagLength: 16" in block(GCM)
rx = re.search(r"metavariable: \$ALG\n\s+regex: (.*)", block(GCM)).group(1)
assert all(re.match(rx, a) for a in ("aes-256-gcm", "aes-128-gcm", "AES-192-GCM", "id-aes256-GCM")), rx
assert not any(re.match(rx, a) for a in ("aes-256-cbc", "aes-256-ctr", "chacha20-poly1305", "gcm", "aes-256-gcm-x")), rx
d, g = block(DATE), block(GCM)
excl = lambda b: (re.search(r"paths:\n\s+exclude: (\[.*\])", b) or [0, 0])[1]
assert excl(d) and excl(d) == excl(block("perun.js.hardcoded-credential-compare")), "date rule skips the credential rules' test paths"
assert d.count("pattern-not-inside:") == 2 and d.count("<... $D.toISOString() ...>") == 2, "round-trip suppression, function and arrow"
assert "pattern-inside" not in d, "no variable-bound forms (precision: they were most of the hits)"
assert g.count("pattern-not: ") == 2 and g.count("authTagLength: $N") == 2, "an authTagLength option exempts the call"
assert "attacker-controlled" in g, "the message states when a short tag matters, not that every message forges"
print("ok")
