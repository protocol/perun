#!/usr/bin/env python3
"""cost_limit_map.py DIR -- heuristic lead-finder for costly or unbounded HTTP endpoints with no rate or quota limit evidence (CWE-770/400). Report-only, stdlib only.

Usage: python3 -I cost_limit_map.py DIR

Read this when you review an API for denial-of-wallet or resource exhaustion: an endpoint that calls an LLM or paid API, takes a file upload, searches, exports, or lets the
client pick the page size costs the owner money or CPU on every call, and an attacker can repeat it without limit. dynamic_probe.py --rate-endpoint sees a missing limit only on a
running app; this is the static side. A row is a lead, never a finding, and SILENCE IS NOT PROOF OF A LIMIT: a gateway, WAF or host may limit where this scan cannot see.

Handlers come from route_auth_map.py (Express/Router/Hono/Fastify, Next route handlers and pages/api, FastAPI, Flask). A handler's text runs from its line to the next
handler of the same file. It is costly when, comments ignored, that text (or its route path) shows one of:
- llm: an OpenAI/Anthropic/Gemini/Mistral/Groq/Cohere/Replicate/ElevenLabs/Vercel-AI-SDK call (`chat.completions`, `messages.create`, `generateText`, `streamText`, `api.openai.com`...);
- upload: multer/busboy/formidable, `formData()`, `req.file(s)`, `request.files` or `UploadFile`;
- search: a `search` route segment; export: an `export` or `report` route segment;
- page-size: `limit`, `pageSize`, `page_size`, `per_page` or `perPage` read from the query string in a handler with no `min`/`max`/`clamp`/`le=`/`MAX_` cap anywhere in it.
Evidence, first hit wins: rate-limit code in the handler's file (rate-limit, ratelimit, limiter, express-rate-limit, @upstash/ratelimit, slowapi, flask-limiter, throttler,
express-slow-down, quota, `429`, too many requests; a bare `throttle` is not evidence), then the same in any scanned file below the package root (nearest ancestor holding
package.json, pyproject.toml, requirements.txt, setup.py, setup.cfg or Pipfile, else DIR).

Rows: TSV on stdout, `file<TAB>line<TAB>rule<TAB>message`, one per costly handler, sorted; plus `unbounded-body` rows (below). missing-cost-limit: no evidence. cost-limit-evidence: evidence found; check it covers the route.
unbounded-body (CWE-770), a handler whose text reads the whole body (`formData()`/`text()`/`arrayBuffer()`/`blob()`, `request.body()`/`get_data()`/`files`, a no-size `.read()` on a request, stream or UploadFile receiver) with no
streamed byte count and no framework limit (bodySizeLimit, bodyLimit, MAX_CONTENT_LENGTH, multer/busboy fileSize...) in its package; the message says "only cap is Content-Length" when the handler checks that header
(a chunked body skips it). Also an express/bodyParser json/urlencoded/raw/text call whose `limit` is infinite or at least 10 MB; a call without `limit` (default 100kb) is not flagged.
stderr: one summary line, or "cost-limit: no HTTP handler found" when route_auth_map finds none. Exit 0; 2 with usage on a bad argument. Reads files only.

ponytail: evidence is package-scoped (a limiter anywhere in the package counts); a handler delegated to another file (`app.post("/x", ctrl.run)`) is judged on its own lines only; gateway
limits are not seen; keyword lists are fixed. Upgrade to per-framework parsing if precision matters more.
"""
import os, re, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from attempt_limit_map import pkgroot, shown, walk  # noqa: E402
from route_auth_map import pymask, read, scan  # noqa: E402
from tenant_scope_check import lineno, mask  # noqa: E402

LLM = re.compile(r"chat\.completions|\.messages\.(?:create|stream)|\.responses\.create|\bgenerate(?:Text|Object)\s*\(|\bstream(?:Text|Object)\s*\(|api\.(?:openai|anthropic|groq|mistral|cohere|elevenlabs)\.|"
                 r"generativelanguage\.googleapis|api\.replicate\.com|\b(?:OpenAI|Anthropic|AsyncOpenAI|AsyncAnthropic|Groq|Cohere|Replicate)\s*\(|ChatCompletion|\bgenerate_content\s*\(|\.invoke\(\s*\{?\s*(?:messages|prompt)", re.I)
UPLOAD = re.compile(r"\b(?:multer|busboy|formidable|multiparty)\b|\.formData\s*\(|\breq\.files?\b|\brequest\.files\b|\bUploadFile\b|\bupload\.(?:single|array|any|fields)\b")
SIZE = re.compile(r"(?:query|searchParams|args|params|Query)[^\n]*\b(?:limit|pageSize|page_size|per_page|perPage)\b|\b(?:limit|pageSize|page_size|per_page|perPage)\b[^\n]*(?:req\.query|searchParams|request\.args|Query\()", re.I)
CAP = re.compile(r"\bmin\(|Math\.min|\bmax\(|Math\.max|clamp|\ble\s*=|\bMAX_|\bmax[A-Z_]\w*", re.I)
SEG = {"search": "search", "export": "export", "exports": "export", "report": "export", "reports": "export"}
EVID = re.compile(r"(?i:rate[-_]?limit|(?<!de)limiter|slowapi|throttler|slow[-_]?down|\bquota|\b429\b|too many requests)")
UB = "unbounded-body"
MISSING = "%s endpoint with no rate or quota limit found in this file or its package (a gateway or host may still limit; confirm with dynamic_probe.py --rate-endpoint)"
WHOLE = re.compile(r"\b(?:req|request|c\.req|ctx\.req)\.(?:formData|text|arrayBuffer|blob)\s*\(\s*\)|\brequest\.(?:body|get_data)\s*\(|\brequest\.files\b")
READ = re.compile(r"\b(?:request|req|stream)\.(?:body\.|stream\(\)\.)?read\(\s*\)")  # plus `await <name>.read()` for a parameter annotated UploadFile; never an fs or open() handle
UPF = re.compile(r"\b(\w+)\s*:\s*UploadFile\b")
STREAM = re.compile(r"(?:getReader\(|for await|iter_bytes|\.on\(\s*[\"']data)[\s\S]*\+=|\+=[\s\S]*(?:getReader\(|for await|iter_bytes)|\.read\(\s*\d")  # a byte count grown while the body streams
CLEN = re.compile(r"content[-_]length", re.I)
FWLIM = re.compile(r"bodySizeLimit|\bbodyLimit\b|body_limit|MAX_CONTENT_LENGTH|MAX_FORM_MEMORY_SIZE|maxFileSize|max_upload_size|sizeLimit|limits\s*:\s*\{[^}]*fileSize")
PARSER = re.compile(r"\b(?:express|bodyParser|body_parser)\.(?:json|urlencoded|raw|text)\(")
LIMIT = re.compile(r"\blimit\s*:\s*([^,}\n]+)")
UNITS = {"kb": 1 << 10, "mb": 1 << 20, "gb": 1 << 30}
BIG = 10 << 20  # a body-parser limit at or above 10 MB (or infinite) is flagged; the 100kb default is not
FOUND = "%s endpoint: limit code found (%s at %s:%d); check it covers this route"


def kinds(text, route):
    """Sorted cost kinds (llm, upload, search, export, page-size) shown by a handler's masked text and route path."""
    k = {SEG[s] for s in re.split(r"[/.]", route.lower()) if s in SEG}
    if LLM.search(text): k.add("llm")
    if UPLOAD.search(text): k.add("upload")
    if SIZE.search(text) and not CAP.search(text): k.add("page-size")  # any cap in the handler (a multi-line `Query(..., le=200)` too) clears it
    return sorted(k)


def declend(lines, ln, py):
    """1-based last line of the handler that starts on line ln: the line before the next top-level declaration (a column-0 line that is no closing bracket), else the last line."""
    i = ln  # 0-based index of the line after the handler's first line
    if py:  # a decorator's own def is at column 0: step past it
        while i <= len(lines) and i - 1 < len(lines) and lines[i - 1].startswith("@"): i += 1
    for j in range(i, len(lines)):
        if lines[j] and lines[j][0] not in " \t})];/": return j
    return len(lines)


def huge(v):
    """True when a body-parser `limit` value text is infinite or at least BIG bytes: '50mb', 1e8, Infinity, 50 * 1024 * 1024. Unreadable values are not flagged."""
    v = v.strip().strip("\"'`").lower()
    if "infinity" in v or "max_safe" in v: return True
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(kb|mb|gb)?", v)
    if m: return float(m.group(1)) * UNITS.get(m.group(2), 1) >= BIG
    n = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", v)]
    return len(n) > 1 and re.fullmatch(r"[\d.\s*]+", v) is not None and eval_prod(n) >= BIG


def eval_prod(n):
    """Product of the numbers n."""
    p = 1.0
    for x in n: p *= x
    return p


def analyze(root):
    """(rows, handlers, costly): sorted (file, line, rule, message) rows for DIR root, the handler count and the count of costly handlers."""
    files, pkgs = walk(root)
    known, rows, texts = set(files), [], {}
    hs = [r for r in scan(root)[0] if r[0] in known]
    for rel in {r[0] for r in hs} | {f for f in files}:
        raw = read(root, rel)
        if raw is not None: texts[rel] = (pymask if rel.endswith(".py") else mask)(raw, True)
    ev = {}
    for rel in sorted(texts):
        x = EVID.search(texts[rel])
        if x: ev[rel] = (x.group(0), lineno(texts[rel], x.start()))
    byfile = {}
    for r in hs: byfile.setdefault(r[0], []).append(r)
    costly = 0
    lim = {}  # package root -> True when a framework body limit is named in a scanned file of it
    for rel in texts:
        pk = pkgroot(rel, pkgs)
        lim[pk] = lim.get(pk, False) or bool(FWLIM.search(texts[rel]))
    for rel in sorted(texts):  # body-parser calls with a huge limit
        for x in PARSER.finditer(texts[rel]):
            y = LIMIT.search(texts[rel][x.end():x.end() + 200].split(")")[0])
            if y and huge(y.group(1)): rows.append((shown(root, rel), lineno(texts[rel], x.start()), UB, "body parser limit: %s allows a huge body (CWE-770); the default is 100kb" % y.group(1).strip()))
    for rel, rs in byfile.items():
        lines = texts[rel].split("\n")
        pk = pkgroot(rel, pkgs)
        for i, (_, ln, _, route, _) in enumerate(rs):
            end = min(rs[i + 1][1] - 1 if i + 1 < len(rs) else len(lines), declend(lines, ln, rel.endswith(".py")))
            body = "\n".join(lines[ln - 1:max(end, ln)])
            whole = WHOLE.search(body) or READ.search(body) or any(re.search(r"\b%s\.read\(\s*\)" % n, body) for n in UPF.findall(body))
            if whole and not STREAM.search(body) and not any(v for k, v in lim.items() if not pk or k == pk or k.startswith(pk + "/")):  # own package and below; a root or sibling limit does not cover it
                rows.append((shown(root, rel), ln, UB, "only cap is Content-Length: a chunked body skips the header check (CWE-770)" if CLEN.search(body) else "whole request body read: no streamed byte count or framework body limit found (CWE-770)"))
            ks = kinds("\n".join(lines[ln - 1:max(end, ln)]), route)
            if not ks: continue
            costly += 1
            what = "/".join(ks)
            h = ev.get(rel) and (rel,) + ev[rel] or next(((f,) + e for f, e in sorted(ev.items()) if not pk or f.startswith(pk + "/")), None)
            out = shown(root, rel)
            rows.append((out, ln, "cost-limit-evidence", FOUND % (what, h[1], shown(root, h[0]), h[2])) if h else (out, ln, "missing-cost-limit", MISSING % what))
    return sorted(rows), len(hs), costly


def main(argv):
    """Print the rows for the directory argv[1] and the summary line on stderr; return 0, or 2 on a usage error."""
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        print("usage: cost_limit_map.py DIR", file=sys.stderr)
        return 2
    rows, n, c = analyze(argv[1])
    for r in rows: print("%s\t%d\t%s\t%s" % r)
    print("cost-limit: %d handlers, %d costly, %d without limit evidence; silence is not proof of a limit" % (n, c, sum(r[2] == "missing-cost-limit" for r in rows)) if n
          else "cost-limit: no HTTP handler found", file=sys.stderr)
    return 0


if __name__ == "__main__": sys.exit(main(sys.argv))
