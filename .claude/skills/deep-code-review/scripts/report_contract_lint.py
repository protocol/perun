#!/usr/bin/env python3
"""Lint a whole-project security audit report against the G0 report contract.

Usage: report_contract_lint.py REPORT.md --root REPO
Template and rules: references/whole-project-report.md.
Exit 0 clean; exit 1 with one `report:line: rule: message` line per violation; exit 2 usage error.
Side effects: none (reads the report and files under --root). Stdlib only.
Edge cases: fenced code blocks are ignored; backtick spans are unwrapped and scanned as prose; the Item column is exempt from the claim scan; a sentence
that negates the claim ("does not say the app is secure") is skipped; a "no vulnerabilities" count
scoped by a tool name prefix or "in <path>" is a tool result, not a safety claim. Cited paths must resolve
inside --root (no `..`, absolute paths or escaping symlinks). The claim list is a regex set, not an
exhaustive paraphrase model; extend CLAIMS when a paraphrase slips through.
"""
import argparse
import os
import re
import sys

STATUSES = {"pass", "fail", "not-checked"}
SECTIONS = {  # rule name -> heading regex
    "missing-table": r"per-standard",
    "missing-not-checked": r"not checked",
    "missing-static-runtime": r"static\W{0,6}(vs|versus)\W{0,6}runtime",
    "missing-dependencies": r"dependenc",
}
RISK = r"(vulnerabilit\w*|weakness\w*|flaws?|findings?|issues?|risks?|problems?)"
# Published safety-claim list (G0); paraphrases matched by pattern.
CLAIMS = [
    r"\b(no|zero|0|without any)\s+([\w-]+\s+){0,3}" + RISK + r"\b",
    r"\bno\s+" + RISK + r"\s+(were\s+|was\s+)?(found|identified|detected|discovered|present)\b",
    r"\b(is|are|was|were|looks|appears|remains|seems|deemed|considered)\b[\s,]+(?:(?!not\b|without\b(?!\s+(?:exception|doubt|question)\b))[\w'-]+[\s,]+){0,5}?(secure|safe|hardened|bulletproof|production[- ]ready|invulnerable|vulnerability[- ]free)\b",
    r"\b(vulnerability|exploit|bug|risk)[- ]free\b",
    r"\b(attack|hack)[- ]proof\b|\bbulletproof\b|\brock[- ]solid\b|\bimpenetrable\b",
    r"\b(safe|ready|cleared?|good) (to|for) (deploy|ship|release|launch|merge|production|use)\b",
    r"\bclean bill of health\b|\bnothing (exploitable|wrong|to fix|to worry)\b",
    r"\bcannot be (hacked|exploited|breached|compromised)\b|\bimpossible to (hack|exploit|breach)\b",
    r"\b(fully|completely|entirely|totally)\s+(secure[d]?|protected|safe|hardened|mitigated)\b",
    r"\b(complies|compliant|conforms|conformant|certified|meets)\b[^.|]{0,40}\b(owasp|asvs|soc ?2|iso ?27001|pci|hipaa|gdpr)\b",
    r"\bnothing (was )?(found|detected|identified)\b|\ball clear\b",
    r"\bfree (of|from) ([\w-]+\s+){0,2}(vulnerabilit\w*|flaws?|weakness\w*|issues?|bugs?)",
    r"\bnot (vulnerable|susceptible|exposed|affected) (to|by)\b",
    r"\b(pass(es|ed)?|clears?|cleared)\s+(all|every|each)\s+([\w-]+\s+){0,2}(checks?|scans?|tests?|audits?|reviews?)\b"
    r"|\b(all|every)\s+([\w-]+\s+){0,2}(checks?|scans?|tests?|audits?)\s+(have\s+|were\s+|are\s+)?(pass\w*|clear\w*)\b",
]
SCOPABLE = {0, 1, len(CLAIMS) - 1}  # tool-result counts: a tool prefix or "in <path>" scopes them
NEGATOR = re.compile(r"(\bnot|\bnever|n't|\bcannot)\s+(claim|say|state|assert|imply|certify|guarantee|mean|show|prove)\w*\b(?:(?!\b(?:but|however|yet)\b)[^.;!?:,])*$")
CITE = re.compile(r"([^\s:#]+)(?::(\d+)(?:-(\d+))?)?")
PROSE_PATH = re.compile(r"/?[\w.-]+(?:/[\w.-]+)*(?:\.\w{1,8})?(?::\d+.*|#L\d+.*)?")
SEP = re.compile(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*")
ROUTE = re.compile(r"/(?:[\w-]+/)*[\w-]+/?")  # HTTP route: leading /, last segment has no extension or :line
CODE = re.compile(r"`([^`]+)`")
SKIP_FILES = {"", "-", "n/a", "none", "—"}


def cells(line):
    """Split a table row on `|`, honoring backtick spans and `\\|`."""
    out, cur, tick, i = [], [], False, 0
    line = line.strip()
    while i < len(line):
        ch = line[i]
        if ch == "\\" and line[i + 1:i + 2] == "|":
            cur.append("|"); i += 2; continue
        if ch == "`":
            tick = not tick
        if ch == "|" and not tick:
            out.append("".join(cur).strip()); cur = []
        else:
            cur.append(ch)
        i += 1
    out.append("".join(cur).strip())
    if line.startswith("|"):
        out = out[1:]
    if line.endswith("|") and not line.endswith("\\|") and out:
        out = out[:-1]
    return out


def resolve(tok, root):
    """Return (realpath, line1, line2, error) for a cited token."""
    m = CITE.fullmatch(tok)
    if not m:
        return None, 0, 0, f"unparseable citation {tok!r}"
    p = m.group(1)
    if os.path.isabs(p) or ".." in p.split("/"):
        return None, 0, 0, f"citation escapes --root: {p}"
    rr = os.path.realpath(root)
    full = os.path.realpath(os.path.join(rr, p))
    if os.path.commonpath([rr, full]) != rr:
        return None, 0, 0, f"citation escapes --root: {p}"
    if not os.path.isfile(full):
        return None, 0, 0, f"cited path does not exist: {p}"
    a, b = (int(g) if g else 0 for g in (m.group(2), m.group(3)))
    if a:
        with open(full, errors="replace") as f:
            n = sum(1 for _ in f)
        if not 1 <= a <= n or (b and not a <= b <= n):
            return None, 0, 0, f"cited line {m.group(2)}{'-' + m.group(3) if b else ''} out of range ({p} has {n} lines)"
    return full, a, b, None


def lint(path, root):
    raw = open(path, errors="replace").read().splitlines()
    live, fence = [], False  # fenced lines are blanked, indexes preserved
    for l in raw:
        if l.lstrip().startswith("```"):
            fence = not fence
            live.append("")
        else:
            live.append("" if fence else l)
    out = []
    add = lambda i, rule, msg: out.append(f"{os.path.basename(path)}:{i + 1}: {rule}: {msg}")
    heads = [(i, len(m.group(1)), m.group(2).strip()) for i, l in enumerate(live) if (m := re.match(r"(#+)\s+(.*)", l))]

    def body(n):  # lines of heading n, up to the next heading of equal or higher level
        i, lv, _ = heads[n]
        end = next((j for j, l2, _ in heads[n + 1:] if l2 <= lv), len(live))
        return i + 1, end

    for rule, rx in SECTIONS.items():
        if not any(re.search(rx, t, re.I) for _, _, t in heads):
            add(0, rule, "required section missing")
    not_run = {}
    for n, (i, _, t) in enumerate(heads):
        if re.search(r"not[ _-]?run", t, re.I):
            a, b = body(n)
            for k in range(a, b):
                if not re.match(r"\s*[-*]\s", live[k]):
                    continue
                m = re.match(r"\s*[-*]\s*`?([\w.-]+)`?\s*(?:[:—-]\s*(\S.*))?$", live[k])
                if not m or not m.group(2):
                    add(k, "not-run-no-reason", f"NOT RUN entry needs `tool: reason`: {live[k].strip()!r}")
                else:
                    not_run[m.group(1).lower()] = m.group(2)
    rows, in_table = [], set()
    for n, (i, _, t) in enumerate(heads):
        if not re.search(SECTIONS["missing-table"], t, re.I):
            continue
        a, b = body(n)
        k = a
        while k < b:
            if not live[k].lstrip().startswith("|"):
                k += 1; continue
            s = k
            while k < b and live[k].lstrip().startswith("|"):
                k += 1
            blk = list(range(s, k))
            hdr = [h.lower() for h in cells(live[s])]
            if len(blk) < 2 or not SEP.fullmatch(live[s + 1].strip()) or "item" not in hdr or "status" not in hdr:
                add(s, "malformed-table", "table needs a header with Item and Status, then a `---` separator row")
                continue
            col = {h: j for j, h in enumerate(hdr)}
            for r in blk[2:]:
                c = cells(live[r])
                rows.append((r, {h: (c[j] if j < len(c) else "") for h, j in col.items()}))
    if not rows:
        add(0, "missing-table", "per-standard table has no rows")
    tools = {w for _, r in rows for w in re.findall(r"[\w.-]+", r.get("basis", "").lower())} | set(not_run)
    unchecked = 0
    for i, r in rows:
        in_table.add(i)
        st = re.sub(r"[\s_]+", "-", re.sub(r"[*`]", "", r.get("status", "")).strip().lower())
        item = r.get("item", "?")
        if st not in STATUSES:
            add(i, "unstatused-item", f"item {item!r} status {st!r} not pass/fail/not-checked")
            continue
        basis = r.get("basis", "").lower()
        toks = set(re.findall(r"[\w.-]+", re.sub(r"guided:[\w.-]+", " ", basis)))
        toks.discard("tool")
        guided = re.search(r"guided:[\w.-]+", basis)
        has_tool = "tool:" in basis
        files, cited = [], []
        for tok in re.split(r"[,;\s]+", r.get("files", "").replace("`", "")):
            if tok.lower() in SKIP_FILES:
                continue
            full, _, _, err = resolve(tok, root)
            if err:
                add(i, "bad-citation", err)
            else:
                cited.append(full)
        if st == "pass":
            if has_tool and toks & set(not_run):
                add(i, "pass-tool-not-run", f"pass for {item!r} but tool {sorted(toks & set(not_run))[0]} is in NOT RUN")
            elif not has_tool and not guided:
                add(i, "pass-no-check", f"pass for {item!r} has no `tool:<name>` or `guided:<id>` basis")
            if guided and not has_tool:
                if not cited:
                    add(i, "guided-pass-no-files", f"guided pass for {item!r} cites no existing file")
                neg = CODE.findall(r.get("negative", ""))
                if not neg:
                    add(i, "guided-pass-no-negative", f"guided pass for {item!r} has no quoted negative")
                else:
                    text = [" ".join(open(f, errors="replace").read().split()) for f in cited]
                    for q in neg:
                        if not any(" ".join(q.split()) in t for t in text):
                            add(i, "guided-pass-negative-not-in-files", f"quoted negative {q!r} not found in a cited file")
        elif st == "not-checked" and not (toks & {k for k, v in not_run.items() if v.strip()}):
            unchecked += 1
    if rows and unchecked / len(rows) > 0.4:
        add(0, "too-many-not-checked", f"{unchecked}/{len(rows)} items not checked without a NOT RUN reason (>40%)")
    # claim scan units: a table row (Item column exempt) or a paragraph (lines joined)
    units, para = [], []
    for i, l in enumerate(live + [""]):
        plain = l.strip() and not re.match(r"#+\s", l) and not l.lstrip().startswith("|") and not SEP.fullmatch(l.strip())
        if plain:
            para.append((i, l.strip()))
            continue
        if para:
            units.append((para[0][0], " ".join(t for _, t in para), [t for _, t in para]))
            para = []
        if i in in_table:
            units.append((i, " | ".join(cells(l)[1:]), []))
    for i, txt, lines in units:
        for t in (tok.strip() for l in lines for tok in CODE.findall(l)):
            if PROSE_PATH.fullmatch(t) and re.search(r"[/:#]", t) and not re.search(r"\s", t) and not ROUTE.fullmatch(t):
                if err := resolve(t, root)[3]:
                    add(i, "bad-citation", err)
        prose = re.sub(r"(?<!\w)[*_~]+|[*_~]+(?!\w)", "", CODE.sub(r"\1", txt))
        for sent in re.split(r"(?<=[.;!?])\s+|\s+\|\s+", " ".join(prose.split())):
            for k, rx in enumerate(CLAIMS):
                for m in re.finditer(rx, sent, re.I):
                    if NEGATOR.search(sent[:m.start(m.lastindex or 0)].lower()):  # negator must reach the claim word
                        continue
                    if k in SCOPABLE:  # a tool result scoped by tool-name prefix or "in <path>"
                        pre = re.match(r"\s*[-*]?\s*`?([\w.-]+)`?\s*[:(]", sent)
                        if (pre and pre.group(1).lower() in tools) or re.search(r"\bin\s+[\w./-]+(\.\w{1,8}\b|/)", sent[m.end():]):
                            continue
                    cookie = re.search(r"\bcookies?\b|httponly|samesite", sent, re.I)
                    if re.search(r"\bSecure\b", m.group(0)) and cookie or re.match(r"\s+(flag|attribute)\b", sent[m.end():], re.I):
                        continue  # cookie attribute, not a claim
                    add(i, "safety-claim", f"safety claim {m.group(0)!r}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    if not os.path.isfile(a.report) or not os.path.isdir(a.root):
        print("usage: report_contract_lint.py REPORT.md --root REPO", file=sys.stderr)
        sys.exit(2)
    v = lint(a.report, a.root)
    print("\n".join(v) if v else "ok")
    sys.exit(1 if v else 0)


if __name__ == "__main__":
    main()
