#!/usr/bin/env python3
"""Tests for the bundled semgrep resource-exhaustion rules in templates/semgrep-taint/js.yml: perun.js.body-cap-after-buffer (request
receiver, non-zero cap, each pattern shape) and perun.js.limiter-key-forwarded-header, both skipping test, fixture and mock paths.

Fixtures are annotated like semgrep's own tests: a `// ruleid: <id>` comment marks the NEXT line as a required finding, an
`// ok: <id>` comment marks the next line as one that must stay clean, and every unannotated line must stay clean too, whichever
rule would report it. All names and values are fictional. RULES=<dir> checks another copy of the rules (used to show the cases
fail without them). The live check needs semgrep and prints SKIP without it (CI installs none); the offline checks always run.
`semgrep --validate` needs the network (it fetches a lint pack), so the live part loads the rules instead: a schema error makes
semgrep report an error and exit non-zero, which a mutated copy below proves. Plain asserts."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")

# Body caps: a size check after the whole body is buffered, or only a declared content-length, is reported.
CAP_TS = r'''
export async function formCap(req: Request) {
  // ruleid: perun.js.body-cap-after-buffer
  const form = await req.formData();
  const file = form.get("file") as File;
  if (file.size > MAX_BYTES) return new Response("too big", { status: 413 });
  return Response.json({ ok: true });
}
export async function inlineFileCap(req: Request) {
  // ruleid: perun.js.body-cap-after-buffer
  const form = await req.formData();
  if ((form.get("file") as File).size > MAX_BYTES) return fail();
  return ok(form);
}
export async function textCap(req: Request) {
  // ruleid: perun.js.body-cap-after-buffer
  const text = await req.text();
  if (text.length > MAX_CHARS) return fail();
  return ok(text);
}
export async function bufferCap(req: Request) {
  // ruleid: perun.js.body-cap-after-buffer
  const buf = await req.arrayBuffer();
  return buf.byteLength > MAX_BYTES ? fail() : ok(buf);
}
export async function jsonCap(req: Request) {
  // ruleid: perun.js.body-cap-after-buffer
  const items = await req.json();
  if (items.length > MAX_ITEMS) return fail();
  return ok(items);
}
export async function declaredLength(req: Request) {
  if (Number(req.headers.get("content-length")) > MAX_BYTES) return fail();
  // ruleid: perun.js.body-cap-after-buffer
  const form = await req.formData();
  return ok(form);
}
export async function declaredLengthVar(req: Request) {
  const len = Number(req.headers.get("Content-Length") ?? "0");
  if (len > MAX_BYTES) return fail();
  // ruleid: perun.js.body-cap-after-buffer
  const body = await req.json();
  return ok(body);
}
export async function countedStream(req: Request) {
  const reader = req.body!.getReader();
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > MAX_BYTES) return fail();
  }
  return ok();
}
export async function declaredLengthThenStream(req: Request) {
  if (Number(req.headers.get("content-length")) > MAX_BYTES) return fail();
  const reader = req.body!.getReader();
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > MAX_BYTES) return fail();
  }
  return ok();
}
export async function noCap(req: Request) {
  // ok: perun.js.body-cap-after-buffer
  const body = await req.json();
  return ok(body);
}
export async function fieldCheck(req: Request) {
  // ok: perun.js.body-cap-after-buffer
  const body = await req.json();
  if (body.name.length > MAX_NAME) return fail();
  return ok(body);
}
export async function otherField(req: Request) {
  // ok: perun.js.body-cap-after-buffer
  const body = await req.json();
  if (body.limit > MAX_LIMIT) return fail();
  return ok(body);
}
export async function otherSize(req: Request) {
  // ok: perun.js.body-cap-after-buffer
  const body = await req.json();
  if (cache.size > MAX_CACHE) cache.clear();
  return ok(body);
}
export async function otherHeader(req: Request) {
  const agent = req.headers.get("user-agent") ?? "";
  if (agent.length > MAX_AGENT) return fail();
  // ok: perun.js.body-cap-after-buffer
  const body = await req.json();
  return ok(body);
}
export async function lengthOnlyLogged(req: Request) {
  log(Number(req.headers.get("content-length")));
  // ok: perun.js.body-cap-after-buffer
  const body = await req.json();
  return ok(body);
}
export async function emptinessCheck(req: Request) {
  // ok: perun.js.body-cap-after-buffer
  const rows = await req.json();
  if (rows.length > 0) return ok(rows);
  return fail();
}
export async function declaredLengthNonZero(req: Request) {
  if (Number(req.headers.get("content-length")) > 0) return ok();
  // ok: perun.js.body-cap-after-buffer
  const body = await req.json();
  return ok(body);
}
export async function responseBody(res: Response) {
  // ok: perun.js.body-cap-after-buffer
  const items = await res.json();
  if (items.length > 0) return ok(items);
  return fail();
}
export async function upstreamCap(res: Response) {
  // ok: perun.js.body-cap-after-buffer
  const items = await res.json();
  if (items.length > MAX_ITEMS) return fail();
  return ok(items);
}
export async function uploadedText(file: File) {
  // ok: perun.js.body-cap-after-buffer
  const text = await file.text();
  if (text.length > MAX_CHARS) return fail();
  return ok(text);
}
export async function receiverNames(c: Context, ctx: Ctx, event: Ev, nextReq: Request) {
  // ruleid: perun.js.body-cap-after-buffer
  const a = await c.req.json();
  // ruleid: perun.js.body-cap-after-buffer
  const b = await ctx.request.text();
  // ruleid: perun.js.body-cap-after-buffer
  const d = await event.request.json();
  // ruleid: perun.js.body-cap-after-buffer
  const e = await nextReq.json();
  if (a.length > MAX_ITEMS || b.length > MAX_CHARS || d.length > MAX_ITEMS || e.length > MAX_ITEMS) return fail();
  return ok();
}
'''

# Rate-limit keys: a forwarded-header read inside a key-deriving function is reported.
LIMIT_TS = r'''
export function getClientKey(req: Request) {
  // ruleid: perun.js.limiter-key-forwarded-header
  return req.headers.get("x-forwarded-for") ?? "unknown";
}
// ruleid: perun.js.limiter-key-forwarded-header
export const rateKey = (req: Request) => req.headers.get("x-real-ip");
export async function getIp(req: Request): Promise<string> {
  // ruleid: perun.js.limiter-key-forwarded-header
  const fwd = req.headers.get("X-Forwarded-For");
  return fwd ? fwd.split(",")[0].trim() : "0.0.0.0";
}
export const limiterKey = async (headers: Record<string, string>) => {
  // ruleid: perun.js.limiter-key-forwarded-header
  return headers["x-forwarded-for"];
};
class Limiter {
  deriveKey(req: Request) {
    // ruleid: perun.js.limiter-key-forwarded-header
    return req.header("x-real-ip");
  }
}
export function logRequest(req: Request) {
  // ok: perun.js.limiter-key-forwarded-header
  console.log(req.headers.get("x-forwarded-for"));
}
export function getClientKeyFromAuth(req: Request) {
  // ok: perun.js.limiter-key-forwarded-header
  return req.headers.get("authorization");
}
export function rateKeyFromProto(req: Request) {
  // ok: perun.js.limiter-key-forwarded-header
  return req.headers.get("x-forwarded-proto");
}
'''

FILES = {"app/api/uploads/route.ts": CAP_TS, "lib/limit.ts": LIMIT_TS}
SKIPPED = {"tests/uploads.ts": CAP_TS, "lib/limit.test.ts": LIMIT_TS}  # test paths are excluded from both rules: nothing in these copies may be reported
ANN = re.compile(r"^\s*//\s*(ruleid|ok):\s*(\S+)\s*$")
META = {"perun.js.body-cap-after-buffer": ("INFO", "getReader()"), "perun.js.limiter-key-forwarded-header": ("INFO", "trusted proxies")}


def annotated(body, kind):
    """(line, rule id) of the line each `// <kind>: <id>` comment points at (the next one)."""
    return {(i + 1, m.group(2)) for i, l in enumerate(body.split("\n"), 1) if (m := ANN.match(l)) and m.group(1) == kind}


ids = lambda kind: {r for b in FILES.values() for _, r in annotated(b, kind)}
assert all(annotated(b, "ok") | annotated(b, "ruleid") for b in FILES.values())  # every fixture is annotated
assert set(META) <= ids("ruleid") & ids("ok"), "a flag and a pass fixture per rule"

if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for p, body in {**FILES, **SKIPPED}.items():
            os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
            open(os.path.join(d, p), "w").write(body)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        scan = lambda cfg: subprocess.run(["semgrep", "--config", cfg, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", *FILES, *SKIPPED],
                                          capture_output=True, text=True, env=env, cwd=d)
        run = scan(RULES)
        r = json.loads(run.stdout)
        # Stand-in for `semgrep --validate` (it needs the network): loading the rules schema-checks them. Prove that check can fail.
        assert run.returncode == 0 and not r["errors"], (run.returncode, r["errors"])
        os.makedirs(os.path.join(d, "bad"))
        js = open(os.path.join(RULES, "js.yml")).read()
        head = "- id: perun.js.body-cap-after-buffer\n  languages: [javascript, typescript]\n  severity: "
        bad = js.replace(head + "INFO\n", head + "LOUD\n", 1)
        assert bad != js, "the body-cap-after-buffer header changed: update the mutation"
        open(os.path.join(d, "bad", "js.yml"), "w").write(bad)
        broken = scan(os.path.join(d, "bad"))
        assert broken.returncode != 0 and json.loads(broken.stdout)["errors"], "a schema error must surface"
    got = set()  # semgrep prefixes a rule id with each local config's directory: keep the perun.<lang>.<name> tail
    for x in r["results"]:
        got.add((x["path"], x["start"]["line"], "perun." + x["check_id"].rsplit("perun.", 1)[-1]))
    want = {(p, ln, rid) for p, body in FILES.items() for ln, rid in annotated(body, "ruleid")}
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
else:
    print("SKIP: semgrep not installed; the live fixture check did not run, the offline checks below do")

# Offline: severity, languages, message and test-path skip of each rule, the ponytail ceiling in the header, every pattern shape, and the
# name, value and receiver regexes each rule carries (semgrep anchors metavariable-regex at the start, like Python's re.match). CI installs
# no semgrep, so every guard the live fixtures prove is pinned here too: dropping one fails this file even when the live part is skipped.
JS = open(os.path.join(RULES, "js.yml")).read()
block = lambda src, rid: src.split(f"- id: {rid}\n")[1].split("\n- id:")[0]
rx = lambda b, mv: re.search(r"metavariable: " + re.escape(mv) + r"\n\s+regex: (.*)", b).group(1)
norm = lambda s: re.sub(r"\s+", " ", s)
excl = lambda b: (re.search(r"paths:\n\s+exclude: (\[.*\])", b) or [0, 0])[1]
for rid, (sev, word) in META.items():
    b = block(JS, rid)
    assert f"  severity: {sev}\n" in b and word in re.search(r"  message: (.*)", b).group(1), rid
    assert "  languages: [javascript, typescript]\n" in b, rid
    assert excl(b) and excl(b) == excl(block(JS, "perun.js.hardcoded-credential-compare")), f"{rid} skips the sibling rules' test, fixture and mock paths"
    assert any(l.startswith("#") and rid.split(".")[-1] in l and "ponytail:" in l for l in JS.split("\n")[:20]), f"header ponytail line for {rid}"

# The pattern skeleton of a rule, whitespace-normalised and with the regex values dropped (those are replayed below): every shape and every
# tag that joins them, so deleting or editing any of them fails here even though only the live part runs semgrep.
skel = lambda b: re.sub(r"(?<!-)(regex:) \S+", r"\1", norm(b)).split(" patterns: ", 1)[1].split(" paths:")[0]
c = block(JS, "perun.js.body-cap-after-buffer")
assert skel(c) == " ".join((
    "- pattern: await $REQ.$M()",
    "- metavariable-regex: metavariable: $REQ regex:",
    "- metavariable-regex: metavariable: $M regex:",
    "- metavariable-regex: metavariable: $N regex:",
    "- pattern-either: - patterns: - pattern-either:",
    "- pattern-inside: | $V = await $REQ.$M(); ... <... $V.$P > $N ...>",  # the result compared in the same block
    "- pattern-inside: | $V = await $REQ.$M(); ... $F = $V.get(...); ... <... $F.$P > $N ...>",  # an entry read from it with get
    "- pattern-inside: | $V = await $REQ.$M(); ... <... $V.get(...).$P > $N ...>",  # an entry compared inline
    "- metavariable-regex: metavariable: $P regex:",
    "- patterns: - pattern-either:",
    '- pattern-inside: | <... (<... $H.get("$CL") ...>) > $N ...>; ... <... await $REQ.$M() ...>',  # a declared length compared first
    '- pattern-inside: | $L = <... $H.get("$CL") ...>; ... <... (<... $L ...>) > $N ...>; ... <... await $REQ.$M() ...>',  # ... through a variable
    "- metavariable-regex: metavariable: $CL regex:")), skel(c)
assert all(re.match(rx(c, "$M"), v) for v in ("formData", "json", "text", "arrayBuffer")) and not any(re.match(rx(c, "$M"), v) for v in ("read", "blob", "jsonp", ""))
assert all(re.match(rx(c, "$P"), v) for v in ("size", "length", "byteLength")) and not any(re.match(rx(c, "$P"), v) for v in ("limit", "count", "name", "sizes", ""))
assert all(re.match(rx(c, "$CL"), v) for v in ("content-length", "Content-Length")) and not any(re.match(rx(c, "$CL"), v) for v in ("content-type", "x-content-length", "content-length-x"))
assert all(re.match(rx(c, "$REQ"), v) for v in ("req", "request", "c.req", "ctx.request", "event.request", "nextReq", "REQ")) and not any(re.match(rx(c, "$REQ"), v) for v in ("res", "response", "file", "form", "r", "seq", "req.clone()", "requestBody")), "the receiver is a request"
assert all(re.match(rx(c, "$N"), v) for v in ("MAX", "1", "10", "1024 * 1024", "0.5")) and not re.match(rx(c, "$N"), "0"), "a comparison with 0 is not a cap"
l = block(JS, "perun.js.limiter-key-forwarded-header")
assert skel(l) == " ".join((
    '- pattern-either: - pattern: $H.get("$HDR") - pattern: $H.header("$HDR") - pattern: $H["$HDR"]',
    "- metavariable-regex: metavariable: $HDR regex:",
    "- pattern-either: - pattern-inside: | function $F(...) { ... }",
    "- pattern-inside: | $F = function (...) { ... }",
    "- pattern-inside: | $F = ($...P) => { ... }",
    "- metavariable-regex: metavariable: $F regex:")), skel(l)
assert all(re.match(rx(l, "$HDR"), v) for v in ("x-forwarded-for", "X-Forwarded-For", "x-real-ip")) and not any(re.match(rx(l, "$HDR"), v) for v in ("x-forwarded-proto", "x-forwarded-for-x", "user-agent", ""))
assert all(re.match(rx(l, "$F"), v) for v in ("getClientKey", "rateKey", "limiterKey", "deriveKey", "getIp", "this.deriveKey")) and not any(re.match(rx(l, "$F"), v) for v in ("handler", "logRequest", "setCookie", "getClientIp", "cacheKey", "createKey", "setIp", "getItem"))
print("ok")
