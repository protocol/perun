#!/usr/bin/env python3
"""Tests for the bundled logging rules (templates/semgrep-taint/logging.yml, OWASP A09:2025): perun.{js,py,go}.log-sensitive (CWE-532, a
sensitive-named value or a whole request body reaching a log sink) and perun.{py,go}.log-injection (CWE-117, request input reaching a log call
unsanitized). Every positive has a clean twin (a redacted, masked or sanitized log).

Fixtures are annotated like semgrep's own tests: `// ruleid: <id>` (`# ruleid:` in Python) marks the NEXT line as a required finding of that rule,
`ok: <id>` marks the next line as one that must stay clean, and every unannotated line must stay clean too. All names and values are fictional.
RULES=<dir> checks another copy of the rules. The live check needs semgrep: it prints SKIP and exits 0 without it, unless REQUIRE_SEMGREP=1
(the real-hub CI job sets it), which fails instead. The offline pins always run. Plain asserts."""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")

JS = '''const logger = require("pino")();
const winston = require("winston");

function handler(req, res, user, password, apiKey) {
  // ruleid: perun.js.log-sensitive
  console.log("login", password);
  // ruleid: perun.js.log-sensitive
  logger.info({ password });
  // ruleid: perun.js.log-sensitive
  logger.info({ user: user.id, token: user.token });
  // ruleid: perun.js.log-sensitive
  winston.error(`bad key ${apiKey}`);
  // ruleid: perun.js.log-sensitive
  console.debug("body " + req.body);
  // ruleid: perun.js.log-sensitive
  logger.warn(req.body);
  // ruleid: perun.js.log-sensitive
  console.log(req.headers.authorization);
  // ruleid: perun.js.log-sensitive
  console.log(req.headers["cookie"]);
  // ok: perun.js.log-sensitive
  logger.info({ password: "[REDACTED]" });
  // ok: perun.js.log-sensitive
  console.log("login", mask(password));
  // ruleid: perun.js.log-sensitive
  console.log("refresh", accessToken);
  // ok: perun.js.log-sensitive
  console.log("board", token);
  // ok: perun.js.log-sensitive
  logger.info("usage", r.usage.total_tokens);
  // ok: perun.js.log-sensitive
  console.log(`max ${maxTokens}`);
  // ok: perun.js.log-sensitive
  console.log("next page", nextPageToken);
  // ruleid: perun.js.log-sensitive
  console.log("refresh", refreshTokens);
  // ok: perun.js.log-sensitive
  console.log("more", nextTokens);
  // ruleid: perun.js.log-sensitive
  console.log("pager", pagerToken);
  // ok: perun.js.log-sensitive
  logger.info({ userId: user.id });
  // ok: perun.js.log-sensitive
  console.log("token refreshed");
  // ok: perun.js.log-sensitive
  logger.info({ hasToken: Boolean(user.token) });
  // ok: perun.js.log-sensitive
  logger.info(redact(req.body));
}
'''

PY = '''import logging

logger = logging.getLogger(__name__)


def login(request, user, password, api_key):
    # ruleid: perun.py.log-sensitive
    logger.info("login %s", password)
    # ruleid: perun.py.log-sensitive
    logging.error(f"bad key {api_key}")
    # ruleid: perun.py.log-sensitive
    logger.debug("token=%s" % user.token)
    # ruleid: perun.py.log-sensitive
    logger.info("payload %s", request.json)
    # ruleid: perun.py.log-sensitive
    # ruleid: perun.py.log-injection
    logger.info("hdr %s", request.headers["Authorization"])
    # ok: perun.py.log-sensitive
    logger.info("login %s", "[REDACTED]")
    # ok: perun.py.log-sensitive
    logger.info("login %s", mask(password))
    # ok: perun.py.log-sensitive
    logger.info("login user=%s", user.id)
    # ok: perun.py.log-sensitive
    logger.info("token refreshed")
    # ok: perun.py.log-sensitive
    logger.info("tokens used: %s", resp.usage.total_tokens)
    # ok: perun.py.log-sensitive
    logger.info(f"max {max_tokens}")
    # ok: perun.py.log-sensitive
    logger.info("next %s", next_page_token)
    # ruleid: perun.py.log-sensitive
    logger.info("issued %s", api_tokens)
    # ok: perun.py.log-sensitive
    logger.info("pages %s", page_tokens)


def search(request):
    # ruleid: perun.py.log-injection
    logger.info("q=%s", request.args.get("q"))
    q = request.args["q"]
    # ruleid: perun.py.log-injection
    logger.warning(f"search {q}")
    ua = request.headers.get("User-Agent")
    # ruleid: perun.py.log-injection
    logging.info("ua %s", ua)
    # ok: perun.py.log-injection
    logger.info("q=%s", request.args.get("q").replace("\\n", " ").replace("\\r", " "))
    # ruleid: perun.py.log-injection
    logger.info("q=%s", request.args.get("q").replace("\\n", " "))
    # ok: perun.py.log-injection
    logger.info("q=%r", repr(q))
    # ok: perun.py.log-injection
    logger.info("page=%s", int(request.args.get("page", 1)))
    # ok: perun.py.log-injection
    logger.info("search done")
'''

GO = '''package bench

import (
	"log"
	"net/http"
	"strconv"
	"strings"
)

func login(w http.ResponseWriter, r *http.Request, password, apiKey string) {
	// ruleid: perun.go.log-sensitive
	log.Printf("login %s", password)
	// ruleid: perun.go.log-sensitive
	log.Println("key", apiKey)
	// ruleid: perun.go.log-sensitive
	// ruleid: perun.go.log-injection
	log.Print(r.Header.Get("Authorization"))
	// ok: perun.go.log-sensitive
	log.Printf("login %s", "[REDACTED]")
	// ok: perun.go.log-sensitive
	log.Printf("login %s", mask(password))
	// ok: perun.go.log-sensitive
	log.Printf("login attempt")
	// ok: perun.go.log-sensitive
	log.Printf("used %d", resp.Usage.TotalTokens)
	// ok: perun.go.log-sensitive
	log.Println("next", nextPageToken)
	// ruleid: perun.go.log-sensitive
	log.Println("tokens", user.Tokens)
	// ok: perun.go.log-sensitive
	log.Println("pages", pageTokens)
}

func search(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.log-injection
	log.Printf("q=%s", r.URL.Query().Get("q"))
	ua := r.Header.Get("User-Agent")
	// ruleid: perun.go.log-injection
	log.Println("ua", ua)
	// ok: perun.go.log-injection
	log.Printf("q=%s", strconv.Quote(r.URL.Query().Get("q")))
	// ok: perun.go.log-injection
	log.Printf("q=%s", strings.ReplaceAll(strings.ReplaceAll(r.FormValue("q"), "\\n", " "), "\\r", " "))
	// ruleid: perun.go.log-injection
	log.Printf("q=%s", strings.ReplaceAll(r.FormValue("q"), "\\r", " "))
	// ok: perun.go.log-injection
	log.Printf("search done")
	f, err := http.Dir("/srv").Open(r.URL.Query().Get("f"))
	_ = f
	// ok: perun.go.log-injection
	log.Println(err)
}
'''

CASES = [("app.js", JS), ("app.py", PY), ("app.go", GO)]
IDS = ["perun.js.log-sensitive", "perun.py.log-sensitive", "perun.go.log-sensitive", "perun.py.log-injection", "perun.go.log-injection"]


def annotated(body, kind):
    """Return {(line of the annotated NEXT line, rule id)} for `// kind: id` / `# kind: id` comments."""
    lines, out = body.splitlines(), set()
    for i, l in enumerate(lines):
        if m := re.match(rf"\s*(?://|#) {kind}: (\S+)$", l):
            j = i + 1
            while re.match(r"\s*(?://|#) (ruleid|ok): ", lines[j]):  # stacked annotations all name the same code line
                j += 1
            out.add((j + 1, m.group(1)))
    return out


want = {n: annotated(b, "ruleid") for n, b in CASES}
ok = {n: annotated(b, "ok") for n, b in CASES}
assert {i for s in want.values() for _, i in s} == set(IDS), "every rule needs a positive fixture"
assert {i for s in ok.values() for _, i in s} == set(IDS), "every rule needs a clean twin"

# Offline pins: every rule has CWE and OWASP A09:2025 metadata, and the injection rules are taint rules with a sanitizer.
text = open(os.path.join(RULES, "logging.yml")).read()
blocks = {b.split("\n")[0].strip(): b for b in re.split(r"(?m)^- id: ", text)[1:]}
assert set(blocks) == set(IDS), sorted(blocks)
for i, b in blocks.items():
    assert re.search(r'cwe: \["CWE-(532|117):', b), i
    assert "A09:2025" in b, i
    if "injection" in i:
        assert "mode: taint" in b and "pattern-sanitizers:" in b, i

if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for n, b in CASES:
            open(os.path.join(d, n), "w").write(b)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--"] + [n for n, _ in CASES],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    for n, _ in CASES:
        got = {(x["start"]["line"], ".".join(x["check_id"].split(".")[-3:])) for x in r["results"] if x["path"] == n}
        assert got == want[n], (n, "unexpected", sorted(got - want[n]), "missed", sorted(want[n] - got))
    print("semgrep-logging: live ok")
elif os.environ.get("REQUIRE_SEMGREP") == "1":
    sys.exit("FAIL: semgrep not installed but REQUIRE_SEMGREP=1, so the live check cannot be skipped")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-logging: ok")
