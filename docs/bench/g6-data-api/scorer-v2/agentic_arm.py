#!/usr/bin/env python3
"""G6 arm (b) driver: run the installed-default Perun security audit on each built G6 fixture, write the --rows JSON.

Usage: agentic_arm.py --detector REPO --out DIR [--fixtures DIR] [--cap 15] [--per-call 3.0] [--set set1]
  Builds the fixtures with <set>/build.py (or uses prebuilt --fixtures DIR, one repo per subdir), then per fixture runs
  `claude -p --plugin-dir <detector>` (the skill under test, never the global install) with ONE fixed, hint-free
  prompt (PROMPT below), model MODEL. Writes DIR/{rows.json, unmapped.json, errors.json, ledger.jsonl, meta.json,
  reports/<fixture>.md, raw/<fixture>.jsonl}; score with: run_and_score.py --rows DIR/rows.json.
  Cost: --max-budget-usd per call = min(--per-call, remaining cap). Before each call the total cap (--cap, default $15) and
  plan-quota utilization (stop at >= 0.8; a missing reading is logged as 'util unknown' and does not stop) are checked. Any crash, cap/quota stop, claude
  error or empty report writes an errors.json entry (and exit 1); rows.json is still written for fixtures that finished.
  DIR must not exist. A paid run: tests (test_agentic_arm.py) use a stub `claude` and never touch set1.

Report parsing (location format = G0 contract, references/whole-project-report.md on branch lane/ready-bar-1103): a
  per-standard table row with status `fail` is a finding, its `path:line` citations (Files cell) are its locations; a
  bullet/numbered line with a `path:line` outside NOT CHECKED / NOT RUN / dependency / static sections is a finding too.
  Under a heading naming routes / endpoints / entry points / inventory, every `path:line` line is a "route_inventory" row.
  Class = run_and_score.classify("agent", "", text); else the generic AGENT_CLASS fallback; else "unmapped" (side file).
"""
import argparse, json, os, re, signal, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_and_score as R

MODEL = "claude-sonnet-5-5"
QUOTA_STOP = 0.8
PROMPT = ("/perun:deep-code-review Security audit of this whole project (FULL scope). Report every security finding with the "
          "file and line, and include an inventory of the HTTP routes and entry points you found.")
ALLOWED = ["Read", "Grep", "Glob", "Skill", "Agent", "Bash(bash *review_checks.sh*)", "Bash(python3 *)", "Bash(git *)", "Bash(grep *)",
           "Bash(rg *)", "Bash(find *)", "Bash(ls *)", "Bash(cat *)", "Bash(sed *)", "Bash(head *)", "Bash(wc *)"]
DENIED = ["Write", "Edit", "NotebookEdit"]
# Fallback only for agent prose that classify() (built for tool rule ids) misses; the route classes are one scored part.
AGENT_CLASS = [
    (r"idor|object.level|ownership|other users?'? (data|records?)|tenant.scope|cross.tenant", "missing_object_check"),
    (r"unauthenticated|(no|missing|without) auth(entication)?\b|authn", "missing_authn"),
    (r"(?<!un)authoriz|privilege|admin.only|role check|authz", "missing_authz"),
    (r"credentials?\b.*\blog(s|ged|ging)?\b|\blog(s|ged|ging)?\b.*\bcredentials?\b", "secret_in_log"),
]
P = r"[\w.\-\[\]()@+]+"  # path segment: word chars . - [ ] ( ) @ +
CITE = re.compile(r"(?<![\w/.:\-])((?:%s/)*%s\.[A-Za-z0-9]{1,8})(?::|#L|\s+lines?\s+|\s+line\s+)(\d+)(?:-L?\d+)?(?![\w/])" % (P, P), re.I)
BARE = re.compile(r"(?<![\w/.:\-])((?:%s/)+%s\.[A-Za-z0-9]{1,8})(?![\w/:])" % (P, P))
ROUTE_H = re.compile(r"^(route inventory|routes|endpoints|entry points)|inventory", re.I)
NOT_ROUTE_H = re.compile(r"finding|auth|issue|vuln|risk", re.I)
SKIP_H = re.compile(r"^(not checked|not run|static|dependenc|fix|remediation|recommend|attack chain)", re.I)
INIT_BAD = "isolation: init skills lack a plugin deep-code-review skill or hold a user-level skill"


class Stop(Exception):
    pass


def cites(s, prefix=""):
    """Text -> ([(file, line)] with line>0, bare_path_seen). Backticks and the fixture abs-path prefix are stripped."""
    s = s.replace("`", "")
    if prefix:
        s = s.replace(prefix.rstrip("/") + "/", "")
    out = []
    for m in CITE.finditer(s):
        f = m[1]
        if f.count("(") > f.count(")"):  # prose paren glued to the path: "(server.js:21)"; keeps app/(auth)/x.ts
            f = f.lstrip("(")
        out.append((f, int(m[2])))
    return out, bool(BARE.search(s))


def classify(text):
    text = re.sub(r"\blog(ged)?[\s-]+(in|on|out)\b", " ", text, flags=re.I)  # "log in" is authentication, not logging
    return R.classify("agent", "", text) or next((c for rx, c in AGENT_CLASS if re.search(rx, text.lower())), None)


def _cols(cs):
    return {c.lower(): i for i, c in enumerate(cs)}


def _first_sentence(flat):
    m = re.search(r"\*\*(.+?)\*\*", flat)
    return (m[1] if m else re.split(r"(?<=[.!?])\s", flat, 1)[0]).strip(". ")


def parse_report(text, fixture, prefix=""):
    """Report markdown -> (rows, unmapped). rows: [{fixture,file,line,class}]; 'route_inventory' for route-list lines.
    Table with a Status column: `fail` rows only; table without one: every row with a cite is a finding. A finding with no
    cite, or a path but no line, goes to unmapped (line 0) with its text, never dropped. Class: title sentence first, then the row."""
    L = text.splitlines()
    rows, unm, seen, head, col, parent = [], [], set(), "", None, []
    for i, ln in enumerate(L):
        if re.match(r"#+\s", ln):
            head, col, parent = re.sub(r"^#+\s*", "", ln).strip(), None, []
            continue
        cs = [c.strip() for c in ln.strip().strip("|").split("|")] if ln.strip().startswith("|") else None
        if cs and set("".join(cs)) <= set("-: "):
            continue
        if cs and i + 1 < len(L) and re.fullmatch(r"[|\s:-]+", L[i + 1].strip()) and "-" in L[i + 1]:
            col = _cols(cs)  # header row: the next line is its separator
            continue
        if SKIP_H.search(head) or not (cs or re.match(r"\s*([-*]|\d+[.)])\s", ln)):
            continue
        flat = re.sub(r"\s+", " ", ln).strip()
        where = ln
        if ROUTE_H.search(head) and not NOT_ROUTE_H.search(head):
            cls = "route_inventory"
        else:
            if cs:
                c = col or {}
                if "status" in c:
                    if c["status"] >= len(cs) or not re.search(r"\bfail", cs[c["status"]], re.I):
                        continue
                for k in ("files", "location", "file", "where"):
                    if k in c and c[k] < len(cs):
                        where = cs[c[k]]
                        break
            cls = classify(_first_sentence(flat)) or classify(flat)
        found, bare = cites(where, prefix)
        if not found and not bare and cs:
            found, bare = cites(ln, prefix)
        if not cs:
            if ln[:1].isspace():  # sub-bullet with no cite of its own inherits its top-level item's; class stays its own text
                if cls and cls != "route_inventory" and not found and not bare and len(parent) == 1:  # multi-cite parent is ambiguous -> unmapped
                    found = parent
            else:
                parent = found
        if cls == "route_inventory":
            if not found:
                continue
        elif not found:  # no usable file:line -> adjudicator, never a file-level row or a drop
            unm.append(dict(fixture=fixture, file="", line=0, **{"class": "unmapped"}, text=flat[:300]))
            continue
        for f, n in found:
            if (f, n, cls) in seen:
                continue
            seen.add((f, n, cls))
            row = {"fixture": fixture, "file": f, "line": n, "class": cls or "unmapped"}
            if cls:
                rows.append(row)
            else:
                unm.append(dict(row, text=flat[:300]))
    return rows, unm


LABEL_CLASS = {"missing-authn": "missing_authn", "missing-authz": "missing_authz", "object-level-authz": "missing_object_check",
               "ssrf": "ssrf", "tls-off": "tls_off", "outbound-timeout": "no_timeout", "secret-in-url": "secret_in_url",
               "secret-in-log": "secret_in_log", "csrf": "csrf", "cookie-flags": "cookie_flags", "rate-limit": "rate_limit",
               "pii-in-log": "pii_log", "pii-data": "pii_data", "prompt-injection": "prompt_injection"}
ITEM = re.compile(r"(?:[-*]|\d+[.)])\s+(?:\[([^\]]*)\])?\s*(.*)")


def parse_report_v2(text, fixture, prefix=""):
    """Report markdown -> (rows, unmapped, out_of_vocab). Scores only what the report claims: top-level `- [label] path:line ...`
    items under a heading starting "Findings", primary cite only (first path:line, before `evidence:`), class from LABEL_CLASS.
    A label outside LABEL_CLASS goes to out_of_vocab (not scored); a vocab item with no label or no path:line goes to unmapped
    (line 0). Sub-bullets and other sections are ignored. Route-inventory rows come from parse_report unchanged."""
    rows = [r for r in parse_report(text, fixture, prefix)[0] if r["class"] == "route_inventory"]
    unm, oov, seen, inside, skip, fence = [], [], set(), 0, False, False  # inside: level of the open Findings heading; ends at a heading of equal/higher level
    for ln in text.splitlines():
        if ln.lstrip().startswith(("```", "~~~")):  # fenced code: no headings or items inside
            fence = not fence
            continue
        h = None if fence else re.match(r"(#+)\s+(.*)", ln)
        if h:
            if not inside or len(h[1]) <= inside:
                inside = len(h[1]) if re.match(r"findings\s*(\(|$)", h[2], re.I) else 0
            skip = bool(inside and len(h[1]) > inside and re.search(r"attack|chain", h[2], re.I))  # chain bullets are not claims
            continue
        m = ITEM.match(ln) if inside and not skip and not fence else None
        if not m:
            continue
        label, body = (m[1] or "").strip().lower(), re.sub(r"\s+", " ", m[2]).strip()
        if label and label not in LABEL_CLASS:
            oov.append(dict(fixture=fixture, label=label, text=body[:300]))
            continue
        found = cites(re.split(r"evidence:", body, 1, flags=re.I)[0], prefix)[0] if label else []
        if not found:
            unm.append(dict(fixture=fixture, file="", line=0, **{"class": "unmapped"}, text=body[:300]))
            continue
        f, n = found[0]
        if (f, n, label) not in seen:
            seen.add((f, n, label))
            rows.append({"fixture": fixture, "file": f, "line": n, "class": LABEL_CLASS[label]})
    return rows, unm, oov


def init_ok(skills):
    """system/init skills list -> True only if a plugin-namespaced deep-code-review skill exists and no user-level skill does.
    Entries are names or dicts {name, path/source}. Shape unverified against a real capture: unknown/empty list fails closed."""
    home = os.path.expanduser("~/.claude")
    names = [(k if isinstance(k, str) else str(k.get("name", ""))) for k in skills or []]
    user = any(isinstance(k, dict) and home in str(k.get("path", "") or k.get("source", "")) for k in skills or []) or "deep-code-review" in names
    return any(n.endswith(":deep-code-review") for n in names) and not user


def sh_claude(prompt, cwd, detector, cap, timeout=1500):
    """One `claude -p` call -> dict(text, cost, util, err, subtype, returncode, stderr, denials, init_skills).
    Streams stdout to a file, kills the process group on timeout, and keeps partial output."""
    cmd = ["claude", "--model", MODEL, "-p", "--plugin-dir", str(detector), "--setting-sources", "project,local",
           "--strict-mcp-config", "--no-session-persistence", "--output-format", "stream-json", "--verbose",
           "--allowedTools", *ALLOWED, "--disallowedTools", *DENIED, "--max-budget-usd", "%.2f" % cap]
    r = dict(text="", cost=0.0, util=None, err="", subtype="", returncode=None, stderr="", denials=[], init_skills=None, skill_loaded=False, raw="")
    with tempfile.TemporaryFile("w+") as so, tempfile.TemporaryFile("w+") as se:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=so, stderr=se, text=True, cwd=cwd, start_new_session=True)
        try:
            p.communicate(prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            r["err"], r["cost"] = "timeout (charged the whole call cap)", cap
        r["returncode"] = p.returncode
        so.seek(0); se.seek(0)
        out, r["stderr"] = so.read(), se.read()[-2000:]
    r["raw"] = out
    root = str(detector).rstrip("/") + "/.claude/skills/deep-code-review/"
    got = False
    for line in out.splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            continue
        t = j.get("type")
        if t == "system" and j.get("subtype") == "init":
            r["init_skills"] = j.get("skills")
        elif t == "assistant" and any(c.get("type") == "tool_use" and (
                (c.get("name") == "Skill" and "deep-code-review" in json.dumps(c.get("input"))) or root in json.dumps(c.get("input")))
                for c in (j.get("message") or {}).get("content", []) if isinstance(c, dict)):
            r["skill_loaded"] = True
        if t == "assistant" and not got:  # partial text kept in case no result event arrives
            r["text"] = "".join(c.get("text", "") for c in (j.get("message") or {}).get("content", []) if isinstance(c, dict))
        elif t == "rate_limit_event":
            info = j.get("rate_limit_info") or {}  # shape seen live: {status, rateLimitType, utilization}; older: unifiedWindows
            us = [v.get("utilization") for v in (info.get("unifiedWindows") or {}).values()] + [info.get("utilization")]
            us = [float(u) for u in us if u is not None]
            if us:
                r["util"] = max([r["util"] or 0.0] + us)
        elif t == "result":
            got = True
            r.update(text=j.get("result") or r["text"], subtype=j.get("subtype") or "", denials=j.get("permission_denials") or [])
            if not r["err"]:
                r["cost"] = float(j.get("total_cost_usd") or 0)
            if j.get("is_error") or str(j.get("subtype", "")).startswith("error"):
                r["err"] = "claude error: %s" % (j.get("subtype") or "is_error")
    r["err"] = r["err"] or ("exit %s, no result event" % r["returncode"] if not got else "" if r["text"].strip() else "empty report")
    if not got:  # crash or kill before the result event: the report is partial and spend unknown, so book the whole call cap
        r["cost"] = cap
    return r


def run(detector, out, fixtures, cap=15.0, per_call=3.0, parser=parse_report_v2):
    """parser: parse_report_v2 (default; 3-tuple, extra list -> out_of_vocab.json) or v1 parse_report (2-tuple)."""
    out = Path(out)
    out.mkdir(parents=True)
    (out / "reports").mkdir()
    (out / "raw").mkdir()
    ledger, rows, unm, oov, errors, spent, util = out / "ledger.jsonl", [], [], [], [], 0.0, 0.0
    json.dump(dict(model=MODEL, prompt=PROMPT, detector=str(detector), cap=cap, per_call=per_call, allowed=ALLOWED,
                   disallowed=DENIED, quota_stop=QUOTA_STOP), open(out / "meta.json", "w"), indent=1)
    try:
        for fx in sorted(p.name for p in Path(fixtures).iterdir() if (p / ".git").exists()):
            left = cap - spent
            if util >= QUOTA_STOP:
                raise Stop("plan quota utilization %.2f >= %s" % (util, QUOTA_STOP))
            if left < 0.05:
                raise Stop("cap $%s: spent %.3f, %.3f left" % (cap, spent, left))
            fdir = Path(fixtures).resolve() / fx
            r = sh_claude(PROMPT, str(fdir), Path(detector).resolve(), min(per_call, left))
            spent += r["cost"]
            if r["util"] is None:
                print("util unknown (no rate_limit_event) after %s" % fx, file=sys.stderr)
            util = max(util, r["util"] or 0.0)
            open(ledger, "a").write(json.dumps({k: v for k, v in r.items() if k not in ("text", "raw")} | dict(
                ts=int(time.time()), fixture=fx, model=MODEL, util_known=r["util"] is not None)) + "\n")
            (out / "reports" / (fx + ".md")).write_text(r["text"])
            (out / "raw" / (fx + ".jsonl")).write_text(r["raw"])
            bad_init = not init_ok(r["init_skills"])
            if r["err"]:
                errors.append(dict(fixture=fx, error=r["err"], subtype=r["subtype"], returncode=r["returncode"], stderr=r["stderr"][-500:]))
            if bad_init:
                raise Stop("%s (fixture %s)" % (INIT_BAD, fx))
            if not r["skill_loaded"]:  # evidence: a Skill tool_use, or a tool_use touching <detector>/.claude/skills/deep-code-review/
                errors.append(dict(fixture=fx, error="skill not loaded"))
            elif not r["err"]:
                a, x, *o = parser(r["text"], fx, str(fdir))
                rows += a
                unm += x
                oov += o[0] if o else []
    except Stop as e:
        errors.append(dict(stop=str(e)))
    except Exception as e:  # crash: record, never silent
        errors.append(dict(crash=repr(e)))
    json.dump(rows, open(out / "rows.json", "w"), indent=1)
    json.dump(unm, open(out / "unmapped.json", "w"), indent=1)
    json.dump(oov, open(out / "out_of_vocab.json", "w"), indent=1)
    json.dump(dict(complete=not errors, errors=errors, spent=round(spent, 4)), open(out / "errors.json", "w"), indent=1)
    return rows, unm, errors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--detector", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fixtures")
    ap.add_argument("--set", default="set1")
    ap.add_argument("--cap", type=float, default=15.0)
    ap.add_argument("--per-call", type=float, default=3.0)
    a = ap.parse_args(argv)
    if a.fixtures:
        return 1 if run(a.detector, a.out, a.fixtures, a.cap, a.per_call)[2] else 0
    with tempfile.TemporaryDirectory() as tmp:
        t = os.path.join(tmp, a.set)
        with tempfile.TemporaryDirectory() as meta:  # the answer key is deleted before the agent runs (it can Read $TMPDIR)
            subprocess.run([sys.executable, str(HERE.parent / a.set / "build.py"), t, "--truth", os.path.join(meta, "truth.json")], check=True)
        return 1 if run(a.detector, a.out, t, a.cap, a.per_call)[2] else 0


if __name__ == "__main__":
    sys.exit(main())
