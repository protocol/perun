#!/usr/bin/env python3
"""comms_lint.py --kind K [--file F] [--source S] [--range R] [--json] | --list — score a human-facing draft against its artifact template.

Kinds, word/line budgets and the optional checks per kind come from the table in references/artifact-templates.md
(the one source of truth; `--list` prints it). Always checked: lead (line 1 is the answer: <=60 words, first
sentence <=35, no greeting/background opener), budget (fails only above BUDGET_SLACK x the table value), dates (a
weekday must fit its date, computed from the calendar), filler (AI-slop phrases), placeholder (TBD, [owner], and the
stand-ins "owner unassigned", "no deadline", "not stated"), vague (numberless "significantly", "on track"). Advisory
WARNs that never put a draft below the bar: hedge, length (over the table value), markers (check/hourglass lines),
numbers (a figure in the first 4 content lines), verified, timezone, and ask (runs only with --source, only when the
source has an ask, and flags a missing owner or date only if the source gives one: nothing demands what the input
lacks). Optional per kind: vocab (status_vocab_lint), timezone
(clock times carry a zone), structure (status_update_lint, leadership form), verified (PR: a check with a result),
command (README: a command). `meeting-notes` drops lead and checks table (open items are rows of Item | Needs | Notes |
Next steps, never bullets above it), numeric (short numeric top-level lines, no emoji, status key or repeated fact),
dri (every row names a DRI or "not set") and links (issue/PR numbers and tracker keys are links; Decided: links the
work). With --source, grounded also flags figures and dates in the draft that the source
never states, and "recommend"/"root cause" claims it never makes, unless the same line marks the figure estimated.
`audit-pr` (the body of an audit, security or hardening PR) adds `sections`, a failing rule at any length: every
AUDIT_SECTIONS heading is present, "What changes for reviewers and users" is not empty (items, or "None"), "Not fixed"
holds counts only (no file:line, route or URL), and, with --range BASE..HEAD, every file the range changes is named
under "Changes by area" by its full path or by a containing directory with a trailing slash. A trailing attribution footer
(a `---` rule or `🤖 Generated` line, then only blank, `---`, `Generated with/by` and `Co-Authored-By:` lines; those lines
may sit in `<sub>`, `<sup>`, `<small>`, `*` or `_` markup) is not part of the last section; any other text after a `---` is
still checked.

Prints `FAIL <rule> L<n>: <problem>. Fix: <exact fix>` per failure and a score line; exit 1 when any non-advisory
rule fails (below the bar), 0 otherwise, 2 on usage, unreadable input or a --range git cannot resolve (fail closed).
API: lint(kind, text, source=None, files=None) -> dict (files: changed paths for the coverage check, None skips it);
changed_files(range) -> [path]. Side effects: reads files only; --range runs read-only `git diff --name-only`.
Limits: regex heuristics on text shape; a clean run proves the shape, never that a number is true. Bodies under
MIN_WORDS skip the structural rules (numbers, ask, markers, verified, command).
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import status_update_lint  # noqa: E402  (also imports status_vocab_lint)
import status_vocab_lint  # noqa: E402

REFERENCE = os.path.join(os.path.dirname(HERE), "references", "artifact-templates.md")
MIN_WORDS = 60  # below this the structural rules would demand ceremony from a one-line body
LEAD_WORDS, SENTENCE_WORDS, LONG_FORM_LABELS = 60, 35, 4
STRUCTURAL = ("numbers", "ask", "markers", "verified", "command")
ADVISORY = ("hedge", "ask", "markers", "length", "numbers", "verified", "timezone")  # WARN, never below the bar: a rule that demands what the input lacks taught stand-ins ("owner unassigned") that readers rejected
BUDGET_SLACK = 1.5  # budget fails only above this multiple of the table value; between 1x and the slack it is a WARN (length)
AUDIT_SECTIONS = ("Summary", "What changes for reviewers and users", "Changes by area", "How to verify", "Not fixed")  # the one home of the audit-pr heading names; the template in artifact-templates.md spells them out
_, S_BEHAVIOR, S_AREAS, _, S_NOT_FIXED = AUDIT_SECTIONS
AUDIT_TITLE = re.compile(r"\b(?:audit\w*|security|harden\w*)\b", re.I)  # a PR title the guard hook checks as `audit-pr`


def load_kinds(path=REFERENCE):
    """{kind: (max_words, max_lines, checks)} parsed from the budgets table; raises ValueError without one."""
    kinds = {}
    with open(path, encoding="utf-8") as f:
        rows = f.read().splitlines()
    for row in rows:
        m = re.match(r"\|\s*`([\w-]+)`\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]*)\|", row)
        if m:
            kinds[m.group(1)] = (int(m.group(2)), int(m.group(3)), tuple(re.findall(r"[a-z]+", m.group(4))))
    if not kinds:
        raise ValueError("no budgets table in " + path)
    return kinds


FILLER = re.compile(r"\b(?:i hope (?:this|you)|hope this helps|just wanted to|i wanted to (?:reach out|share|let you know|follow up)|"
                    r"(?:please )?(?:do not|don't|don’t) hesitate|feel free to|let me know if you (?:have|need|want)|happy to help|"
                    r"great (?:question|point)|you(?:'|’)re (?:absolutely )?right|"
                    r"thanks? (?:so much|a lot|for (?:your|the) (?:patience|time))|it(?:'|’)s worth (?:noting|mentioning)|"
                    r"it is worth (?:noting|mentioning)|needless to say|at the end of the day|in conclusion|in summary|to summari[sz]e|"
                    r"comprehensive|robust|seamless(?:ly)?|leverag(?:e|es|ed|ing)|delve|streamlin(?:e|es|ed|ing)|cutting[- ]edge|"
                    r"state[- ]of[- ]the[- ]art|best[- ]in[- ]class|game[- ]chang(?:er|ing)|revolutionary|powerful|blazing(?:ly)?[- ]fast|"
                    r"effortless(?:ly)?|excited to|thrilled|pleased to announce|holistic|synerg\w+|going forward|moving forward)\b", re.I)
HEDGE = re.compile(r"\b(?:it depends|i think maybe|could potentially|might potentially|perhaps|kind of|sort of|somewhat|i guess)\b", re.I)
VAGUE = re.compile(r"\b(?:significantly|substantially|dramatically|drastically|considerably|greatly|much (?:faster|slower|better|worse|more|less)|"
                   r"(?:vast|great) majority|majority of|mostly|nearly|almost all|on track|going well|(?:good|great|strong) progress|"
                   r"a lot of|lots of|numerous|huge|massive|(?:major|large|big) improvements?|(?<!statistically )significant)\b", re.I)
PLACEHOLDER = re.compile(r"\bTBD\b|\bTODO\b|\bXXX+\b|\blorem ipsum\b|\[(?:owner|date|name|link|number|your name|insert[^\]]*)\]|"
                         r"<(?:owner|date|name|link|number|who|when)>|\bowner unassigned\b|\bunassigned owner\b|"
                         r"\bno deadline(?: given| set| stated)?\b|\bnot (?:stated|specified)\b|\bnone given\b", re.I)
OPENER = re.compile(r"^(?:hi|hello|hey|dear|thanks?|thank you|hope|i (?:just |wanted|am writing|['’]m writing)|just\b|(?:a )?quick\b|"
                    r"as (?:discussed|per|promised|requested)|following up|per our|so[, ]|"
                    r"this (?:pr|pull request|update|email|message|document|doc|note|section) (?:is|will|aims|provides|describes|covers|contains|summari[sz]es)|"
                    r"here(?:['’]s| is| are)|below (?:is|are)|in this (?:pr|pull request|update)|background\b|context\b|currently,|previously,|"
                    r"historically|overview\b|introduction\b)", re.I)
# lines that carry no answer: headings, rules, greetings, subject lines, bare labels (`Summary:` or `**Summary**`)
SKIP = re.compile(r"^\s{0,3}#{1,6}\s|^\s*(?:[-*_]\s*){3,}$|^\W*(?:hi|hello|hey|dear)\b[\w ,]{0,28}[,:!]?\W*$|^\W*\w+,\W*$|"
                  r"^\W*subject\s*:|^[\s>*_-]*(?:\*\*|__)?[\w /&-]{2,30}:?(?:\*\*|__)?:?\s*$(?<=:)|^\s*<!--|"
                  r"^[\s>*_-]*(?:\*\*|__)[\w /&-]{2,30}:?(?:\*\*|__)\s*$", re.I)
MONTH = (r"(?:january|february|march|april|may|june|july|august|september|october|november|december|"
         r"jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)\.?")
DATE = re.compile(rf"\b\d{{4}}-\d{{2}}-\d{{2}}\b|\b\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?\b|\b{MONTH}\s+\d{{1,2}}\b|\b\d{{1,2}}\s+{MONTH}\b|"
                  r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thurs|fri|sat|sun)\b|"
                  r"\b(?:today|tomorrow|tonight|eod|cob|end of (?:day|week|month|quarter|sprint)|next (?:week|month))\b", re.I)
ROLE = re.compile(r"@\w+|\b(?:you|your|team|reviewer|approver|owner|dri|manager|director|vendor|finance|legal|support|security|sales|"
                  r"customers?|admins?|users?|everyone)\b", re.I)
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DAYDATE = re.compile(rf"\b(mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:rs?|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\.?,?\s+(?:(\d{{4}})-(\d{{1,2}})-(\d{{1,2}})|(\d{{1,2}})/(\d{{1,2}})(?:/(\d{{4}}))?|"
                     rf"({MONTH})\s+(\d{{1,2}})(?:,?\s+(\d{{4}}))?)", re.I)
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
NOT_NAMES = {"Decision", "Needed", "Action", "Ask", "Recommend", "Recommended", "Reply", "Approve", "Option", "Options", "None", "Please",
             "Need", "Confirm", "Review", "Sign", "Choose", "Pick", "Decide", "Required", "Customer", "Next", "Approval", "Today",
             "Tomorrow", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "January", "February", "March",
             "April", "June", "July", "August", "September", "October", "November", "December"}
ASK = re.compile(r"^\W*(?:ask|asks|decision needed|decision|action required|action needed|action|customer action|your action|"
                 r"approval needed|approval|review ask|needed from [\w ]+)\b[^:\n]{0,40}(?::|\W*$)", re.I)
IMPLICIT_ASK = re.compile(r"\b(?:please|needs? (?:your|you|a|an) |can you|could you|would you|approv(?:e|al)|sign[- ]?off|waiting (?:on|for)|"
                          r"blocked (?:on|by)|awaiting|your (?:review|input|call|decision))\b", re.I)
NONE = re.compile(r"^\W*(?:none|no (?:decision|action|ask)(?: needed| required)?|n/a|nothing)\b", re.I)
STATE = re.compile(r"\b(?:verified|tested|measured|confirmed|merged|deployed|passing|passed|checked|reproduced)\b|\d+\s*(?:/|of)\s*\d+", re.I)
CLOCK = re.compile(r"\b\d{1,2}:\d{2}\b")
ZONE = re.compile(r"UTC|GMT|Z\b|(?!AM\b|PM\b)[A-Z]{2,4}\b|[+-]\d{2}:?\d{2}\b")
ZONE_UNKNOWN = re.compile(r"\b(?:zone|timezone) (?:not given|unknown)|\blocal time\b", re.I)
VERIFY = re.compile(r"✅|⏳|\bverified\b|\btests?\b|\bran\b|\bbenchmark\w*", re.I)
RESULT = re.compile(r"\d|\b(?:pass(?:es|ed)?|green|clean)\b", re.I)
ESTIMATE = re.compile(r"~|[×=]|\d\s*x\s*\$?\d|\b(?:about|roughly|approx\w*|estimat\w*|extrapolat\w*|infer\w*|assum\w*|expect\w*|scaled?|derived|calculated)\b", re.I)
CLAIMS = (("recommend", re.compile(r"\brecommend\w*", re.I)), ("prevent", re.compile(r"\bwould have (?:prevented|avoided)\b", re.I)),
          ("root cause", re.compile(r"\broot cause\b", re.I)), ("guarantee", re.compile(r"\bguarantee[sd]?\b", re.I)))
LABELLED = re.compile(r"\b(?:option|step|phase|point|item|section|part|tier|level|v)\s*\d+\b", re.I)
NUMWORDS = {w: str(i) for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}
NUMWORDS.update(twenty="20", thirty="30", forty="40", fifty="50", hundred="100", thousand="1000", dozen="12")


def _prose(text):
    """[(line_no, text)] of non-blank lines outside fenced code."""
    out, fence = [], False
    for i, ln in enumerate(text.splitlines(), 1):
        if ln.lstrip().startswith("```"):
            fence = not fence
        elif not fence and ln.strip():
            out.append((i, ln))
    return out


def _clean(ln):
    return re.sub(r"^[\s>*+•-]+|\*\*|__|`", "", ln).strip()


def _words(s):
    return len(s.split())


def _skip(ln):
    """True for a line that carries no answer (heading, rule, greeting, subject, bare label)."""
    s = ln.strip()
    return bool(SKIP.search(s)) and not re.search(r"\d", s)


def _owner(s):
    return bool(ROLE.search(s) or [w for w in re.findall(r"\b[A-Z][a-z]{2,}\b", s) if w not in NOT_NAMES])


def _figures(s, words=False):
    """Digit strings in s (commas stripped; list indices and 'option 2' labels ignored); words=True adds spelled-out small numbers."""
    s = LABELLED.sub("", re.sub(r"(?m)^\s*\d+[.)]\s+", "", s))
    nums = {m.replace(",", "") for m in re.findall(r"\d[\d,]*(?:\.\d+)?", s)}
    return nums | ({NUMWORDS[w] for w in re.findall(r"[a-z]+", s.lower()) if w in NUMWORDS} if words else set())


def _bad_weekdays(prose):
    """[(line_no, text, real weekday)] for 'Wed 10/22' style mentions whose weekday does not fit the date (this year or
    next when the text gives no year). Computed from the calendar, so a wrong day-of-week is never repeated."""
    out, this = [], datetime.date.today().year
    for n, ln in prose:
        for m in DAYDATE.finditer(ln):
            wd = [i for i, d in enumerate(WEEKDAYS) if d.startswith(m.group(1).lower()[:3])][0]
            if m.group(2):
                y, mo, d = int(m.group(2)), int(m.group(3)), int(m.group(4))
            elif m.group(5):
                mo, d, y = int(m.group(5)), int(m.group(6)), int(m.group(7) or 0)
            else:
                mo, d, y = MONTHS.index(m.group(8).lower()[:3]) + 1, int(m.group(9)), int(m.group(10) or 0)
            try:
                days = [datetime.date(yy, mo, d).weekday() for yy in ([y] if y else [this, this + 1])]
            except ValueError:
                continue
            if wd not in days:
                out.append((n, m.group(0), WEEKDAYS[days[0]].capitalize()))
    return out


def _hit(n, problem, fix):
    return {"line": n, "problem": problem, "fix": fix}


EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⏳✅]")
KEY = re.compile(r"[A-Z][A-Z0-9]+-\d+")
LINK = re.compile(r"\[[^\]]*\]\([^)]*\)|https?://\S+|`[^`]*`")
TOP_WORDS = 20


def _meeting(res, prose):
    """meeting-notes rules: open items are table rows (table), short numeric top-level lines with no emoji, status key or
    repeated fact (numeric), a DRI on every row (dri), issue/PR numbers and tracker keys as links (links)."""
    hdr = next((i for i, (_, ln) in enumerate(prose) if "|" in ln and all(w in ln.lower() for w in ("item", "needs", "notes", "next steps"))), None)
    if hdr is None:
        res["table"].append(_hit(None, "no `Item | Needs | Notes | Next steps` table", "put every open item as a row of that table"))
    top = prose[:hdr] if hdr is not None else prose
    for n, ln in top:
        if re.match(r"\s*[-*+•]\s", ln):
            res["table"].append(_hit(n, "open item as a bullet above the table", "move it into a table row: one question in Needs, status in Notes"))
    seen = {}
    for n, ln in prose:
        s = ln.strip()
        if EMOJI.search(s):
            res["numeric"].append(_hit(n, "emoji", "delete it; this kind has no emoji or status key"))
        if re.match(r"\W*(?:status key|legend|key)\b", s, re.I):
            res["numeric"].append(_hit(n, "status key", "delete the key"))
        norm = re.sub(r"\W+", " ", s.lower()).strip()
        if len(norm.split()) >= 4:
            if norm in seen:
                res["numeric"].append(_hit(n, f"repeats line {seen[norm]}", "state each fact once; delete the repeat"))
            seen.setdefault(norm, n)
    for n, ln in top:
        if not _skip(ln) and not ln.lstrip().startswith("|"):
            if _words(ln) > TOP_WORDS or not re.search(r"\d", ln):
                res["numeric"].append(_hit(n, "top-level line is long or has no number", f"one line per item: number plus decision, {TOP_WORDS} words or fewer"))
    for n, ln in prose[hdr + 1:] if hdr is not None else []:
        if ln.lstrip().startswith("|") and not re.fullmatch(r"[\s|:-]+", ln):
            m = re.search(r"DRI\s*[:=-]\s*([^|;,.]*)", ln, re.I)
            if not (m and m.group(1).strip()):
                res["dri"].append(_hit(n, "row has no DRI", "add `DRI: <name>`, or `DRI: not set`; never blank"))
    for n, ln in prose:
        bare = LINK.sub("", ln)
        for m in re.finditer(r"(?<![\w/])#\d+|(?<![\w/-])" + KEY.pattern, bare):
            res["links"].append(_hit(n, f"'{m.group(0)}' is not a link", "write it as [text](url)"))
        if re.search(r"\bDecided:", ln) and not re.search(r"\]\(|https?://", ln):
            res["links"].append(_hit(n, "Decided: line has no link", "link where the work lives; no old-plan history"))


HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(\S.*)$")  # the name is cleaned by _name: one regex for the whole tail backtracks without bound on a long run of spaces
# detail a public PR must not carry about an unfixed finding: file:line, a line reference, an HTTP route, a URL, a file path
# (the path part is bounded: unbounded it rescans a long token from every start and goes quadratic)
DETAIL = re.compile(r"\.[A-Za-z]\w{0,7}:\d+|#L\d+|\blines?\s+\d+|\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+/|"
                    r"(?<![\w/:.-])/[\w.-]+|\bhttps?://|\b[\w.-]{1,100}/[\w./-]{0,200}\.[A-Za-z]\w{0,7}\b")
# one attribution-footer line, matched whole: a `---` rule or `🤖 Generated ...` (either starts a footer), `Generated with/by ...`,
# `Co-Authored-By: ...` or nothing. The `🤖 Generated`, `Generated with/by` and `Co-Authored-By:` shapes may open in <sub>, <sup>, <small>, `*` or `_` markup (the closer is part of the tail).
# ponytail: a line is judged by its prefix, so detail on a `Generated ...` or `Co-Authored-By:` line goes unchecked; tighten the shapes if that is abused
_MARKUP = r"(?:</?(?:sub|sup|small)>|[*_]){0,6}"  # bounded: an unbounded repeat would be quadratic on a long run of `*`
FOOTER = re.compile(r"(?:(?P<mark>-{3,}|" + _MARKUP + r"🤖[\s*_]*Generated\b.*)|" + _MARKUP + r"Generated (?:with|by)\b.*|" + _MARKUP + r"Co-Authored-By:.*)?", re.I)


def _name(text):
    """A heading's text as a section key: closing #s, a trailing colon and **/__ emphasis dropped, spaces collapsed, lower-cased."""
    text = re.sub(r"^(\*\*|__)(.*)\1$", r"\2", text.rstrip().rstrip("#").rstrip().rstrip(":").rstrip())
    return " ".join(text.rstrip(":").split()).lower()


def _blank_comments(text):
    """`text` with each terminated `<!-- ... -->` replaced by its newlines, so line numbers stay put; an unterminated `<!--`
    stays as written. str.find, not re.sub(r"<!--.*?-->"): that rescans to the end of the text from every `<!--`, which is
    quadratic on a body of unterminated ones. Once one `<!--` has no `-->` after it, no later one has either."""
    out, i = [], 0
    while (a := text.find("<!--", i)) >= 0 and (b := text.find("-->", a + 4)) >= 0:
        out += (text[i:a], "\n" * text.count("\n", a, b))
        i = b + 3
    return "".join(out) + text[i:]


def _sections(text):
    """{heading name lower-cased: (line_no, [(line_no, line)])} for each markdown heading outside fenced code. A section
    runs to the next heading of the same or a higher level (sub-headings stay inside it); the first of a repeated heading
    wins; HTML comments are dropped, so a template hint is not content. A trailing attribution footer is not content either:
    the last section ends at the first `---` rule or `🤖 Generated` line that is followed only by FOOTER-shaped lines (blank,
    `---`, `Generated with/by ...`, `Co-Authored-By: ...`, in markup or not) to the end; any other text after a rule keeps the rule as content."""
    lines = _blank_comments(text).splitlines()
    heads, fence, foot = [], False, len(lines)
    for i, ln in enumerate(lines):
        fence ^= ln.lstrip().startswith("```")
        m = None if fence else HEADING.match(ln)
        f = None if fence else FOOTER.fullmatch(ln.strip())
        if m:
            heads.append((i, len(m.group(1)), _name(m.group(2))))
        if m or not f:
            foot = len(lines)  # a heading or any non-footer line (fence lines included) after a rule makes that rule content
        elif f["mark"] and foot == len(lines):
            foot = i
    lines = lines[:foot]
    out = {}
    for k, (i, level, name) in enumerate(heads):
        end = next((j for j, lv, _ in heads[k + 1:] if lv <= level), len(lines))
        out.setdefault(name, (i + 1, [(n + 1, lines[n]) for n in range(i + 1, end)]))
    return out


def _covers(area, path):
    """True when `area` names repo path `path` as a whole path (not part of a longer one) or a directory holding it, written
    with a trailing slash. Whole = not glued to a path character (a word character or one of @ + ~ / . -) on the left (a `./`
    may sit between) or on the right (a `.` may follow unless a word character does). str.find, not a regex: files x area bytes stays fast."""
    sep = lambda ch: not (ch.isalnum() or ch in "_@+~/.-")  # noqa: E731
    parts = path.split("/")
    for c in [path] + ["/".join(parts[:i]) + "/" for i in range(1, len(parts))]:
        i = area.find(c)
        while i >= 0:
            pre, post = area[max(i - 3, 0):i], area[i + len(c):i + len(c) + 2]
            left = not pre or sep(pre[-1]) or (pre[-2:] == "./" and (len(pre) < 3 or sep(pre[0])))
            right = not post or ((sep(post[0]) or post[0] == ".") and not (post[0] == "." and len(post) > 1 and (post[1].isalnum() or post[1] == "_")))
            if left and right:
                return True
            i = area.find(c, i + 1)
    return False


def _audit(hits, text, files):
    """The audit-pr `sections` rule: every AUDIT_SECTIONS heading is present, S_BEHAVIOR is not empty, S_AREAS names every
    path in `files` (when given), S_NOT_FIXED carries no DETAIL. Appends to `hits`."""
    sec = _sections(text)
    for name in AUDIT_SECTIONS:
        if name.lower() not in sec:
            hits.append(_hit(None, f"no `## {name}` section", f"add `## {name}`; the audit-pr template is in references/artifact-templates.md"))
    n, body = sec.get(S_BEHAVIOR.lower(), (None, []))
    if n and not any(re.search(r"\w", t) for _, t in body):
        hits.append(_hit(n, f"`{S_BEHAVIOR}` is empty", "list every noticeable change as a bullet, or write `None` when every change is internal"))
    n, body = sec.get(S_AREAS.lower(), (None, []))
    area = "\n".join(t for _, t in body)
    miss = [f for f in files or () if n and not _covers(area, f)]
    if miss:
        more = f" (+{len(miss) - 5} more)" if len(miss) > 5 else ""
        hits.append(_hit(n, f"{len(miss)} changed file(s) not named under `{S_AREAS}`: {', '.join(miss[:5])}{more}",
                         "name each by its full path, or by a directory that contains it with a trailing slash (`src/api/`)"))
    for n, t in sec.get(S_NOT_FIXED.lower(), (None, []))[1]:
        m = DETAIL.search(t)
        if m:
            hits.append(_hit(n, f"`{S_NOT_FIXED}` carries detail ('{m.group(0).strip()}')",
                             "give counts by severity only, for example `2 high, 5 medium, tracked privately`; no file:line, route or exploit detail"))


def changed_files(rng, cwd=None):
    """Repo-relative paths changed in git range `rng`. `A..B` and `A...B` both mean B against merge-base(A, B), the files a PR
    carries; a bare `A` means `A...HEAD`. Raises ValueError when git cannot resolve the range, so callers choose to fail closed or open."""
    if not rng or rng.startswith("-"):
        raise ValueError(f"bad range {rng!r}")
    rng = re.sub(r"(?<!\.)\.\.(?!\.)", "...", rng)
    rng += "" if "..." in rng else "..."
    p = subprocess.run(["git", "diff", "--name-only", "--no-renames", "-z", rng, "--"], cwd=cwd, capture_output=True, text=True)
    if p.returncode:
        raise ValueError(f"git diff {rng}: " + (p.stderr.strip().splitlines() or ["failed"])[0])
    return [f for f in p.stdout.split("\0") if f]


def lint(kind, text, source=None, files=None):
    """Score `text` as artifact `kind` (see load_kinds). Returns {kind, ok, score:[passed, total], words, lines,
    budget:[words, lines], rules:[{rule, ok, advisory, hits:[{line, problem, fix}]}]}. Pure apart from reading the
    table. `status` text with LONG_FORM_LABELS or more leadership labels is checked as `leadership`. `files` (paths
    changed by the PR, from changed_files) turns on the audit-pr coverage check; None skips it, [] has nothing to cover.
    Raises KeyError for a kind outside the table."""
    kinds = load_kinds()
    if kind == "status" and sum(1 for ln in text.splitlines() if status_update_lint.LABEL.match(ln)) >= LONG_FORM_LABELS:
        kind = "leadership"
    max_words, max_lines, checks = kinds[kind]
    prose = _prose(text)
    words = sum(_words(t) for _, t in prose)
    body = [(n, _clean(t)) for n, t in prose if not _skip(t)]
    lead = body[0] if body else None
    res = {"lead": [], "budget": [], "filler": [], "placeholder": [], "vague": [], "hedge": []}
    if "nolead" in checks:
        del res["lead"]
        res.update({r: [] for r in ("table", "numeric", "dri", "links")})
    res.update({r: [] for r in STRUCTURAL if r in checks and words >= MIN_WORDS})
    res.pop("ask", None)  # non-forcing: the ask check runs only when the source has an ask (below)
    src_asks = source is not None and words >= MIN_WORDS and ("ask" in checks or "askif" in checks) and (
        IMPLICIT_ASK.search(source) or any(ASK.search(ln) for ln in source.splitlines()))
    if src_asks:
        res["ask"] = []
    res.update({r: [] for r in ("vocab", "timezone", "structure", "sections") if r in checks})  # sections is neither STRUCTURAL nor ADVISORY: it runs at any length and fails
    if source is not None:
        res["grounded"] = []

    if "table" in res:
        _meeting(res, prose)
    if "sections" in res:
        _audit(res["sections"], text, files)
    if "lead" not in res:
        pass
    elif lead is None:
        res["lead"].append(_hit(1, "no content line", "write the answer on line 1: outcome + number + ask, 30 words or fewer"))
    else:
        n, ln = lead
        first = re.split(r"(?<=[.!?])\s+", ln, maxsplit=1)[0]
        if OPENER.search(ln):
            res["lead"].append(_hit(n, f"line opens with '{ln[:30]}' (greeting, background or preamble)",
                                    "delete the opener; start with the outcome, the number and the ask"))
        if _words(ln) > LEAD_WORDS or _words(first) > SENTENCE_WORDS:
            res["lead"].append(_hit(n, f"lead is {_words(ln)} words (first sentence {_words(first)}); the answer is buried",
                                    f"rewrite line {n} as one sentence of {SENTENCE_WORDS} words or fewer: outcome + number + ask; move the rest below it"))
    over = f"{words} words / {len(prose)} lines against {max_words} / {max_lines} for {kind}"
    cut = f"cut {max(words - max_words, 0)} words and {max(len(prose) - max_lines, 0)} lines: drop process narration and background, move detail behind one link; keep every fact the reader needs"
    if words > max_words * BUDGET_SLACK or len(prose) > max_lines * BUDGET_SLACK:
        res["budget"].append(_hit(None, over, cut))
    elif words > max_words or len(prose) > max_lines:
        res["length"] = [_hit(None, over, cut)]  # advisory: a ceiling at BUDGET_SLACK x, so a needed fact is never cut for the target
    res["dates"] = [_hit(n, f"'{m}' is a {day}", "check the date: fix the weekday or the date, or ask the author") for n, m, day in _bad_weekdays(prose)]
    for rule, rx, fix in (("filler", FILLER, "delete the phrase"), ("placeholder", PLACEHOLDER, "delete it, or fill it from the source; leave an unknown part out instead of writing a stand-in")):
        res[rule] = [_hit(n, f"'{rx.search(ln).group(0)}'", fix) for n, ln in prose if rx.search(ln)]
    for n, ln in prose:
        for sent in re.split(r"(?<=[.!?;])\s+", ln):
            m = VAGUE.search(sent)
            if m and not re.search(r"\d", sent):
                res["vague"].append(_hit(n, f"'{m.group(0)}' with no number", f"replace '{m.group(0)}' with the measured value (X → Y or X of Y), or say it is unmeasured"))
    res["hedge"] = [_hit(n, f"'{HEDGE.search(ln).group(0)}'", "state the position, or name the specific unknown") for n, ln in prose if HEDGE.search(ln)]

    if "numbers" in res and not any(re.search(r"\d", t) for _, t in body[:4]):
        res["numbers"].append(_hit(lead[0], "no figure in the first 4 content lines",
                                   "add the number that matters (X → Y, X of Y, a count or a date); if none is known, say what is unmeasured"))
    if "ask" in res:
        asks = [(n, ln) for n, ln in prose if ASK.search(ln) or IMPLICIT_ASK.search(ln)]
        if not asks:
            res["ask"].append(_hit(None, "the source asks something but the draft does not", "state the ask, with the owner and date the source gives"))
        for n, ln in [a for a in asks if ASK.search(a[1])]:  # owner and date are judged on labelled ask lines only
            val = ln.split(":", 1)[1].strip() if ":" in ln else ""  # a bare heading takes its value from the next line
            nxt = "" if val else next((t for m, t in prose if m == n + 1), "")
            full, val = ln + " " + nxt, val or nxt
            miss = [w for w, ok, given in (("a date", DATE.search(full), DATE.search(source)), ("an owner", _owner(full), _owner(source)))
                    if not ok and given]  # only what the source itself contains
            if miss and not NONE.search(val):
                res["ask"].append(_hit(n, "ask lacks " + " and ".join(miss), "name the owner and date if the source gives them; if it gives none, leave them out (never 'owner unassigned', 'no deadline')"))
    if "markers" in res:
        marks = [(n, ln) for n, ln in prose if "✅" in ln or "⏳" in ln]
        if not marks:
            res["markers"].append(_hit(None, "no ✅/⏳ status line", "mark a verified outcome ✅ (name the surface) and a pending one ⏳; leave neutral facts (churn, risks) unmarked"))
        for n, ln in marks:
            rest = re.sub(r"^\W*(?:✅|⏳)\W*\S+\s*", "", ln)
            if "⏳" in ln and not (DATE.search(ln) and _owner(rest)):
                res["markers"].append(_hit(n, "⏳ line lacks an owner or a date", "add them if the source gives them; otherwise leave them out"))
            if "✅" in ln and not STATE.search(ln):
                res["markers"].append(_hit(n, "✅ line names no evidence", "say merged, deployed, tested or verified on <surface>; otherwise use ⏳"))
    if "vocab" in res:
        res["vocab"] = [_hit(n, f"'{p}' with no verified-on-<page> or journey: reference", "write 'merged', 'deployed, unverified', or add `verified-on-<page>`")
                        for n, p in status_vocab_lint.lint(text) if not re.search(r"nothing.*\blive", text.splitlines()[n - 1], re.I)]
    if "timezone" in res:
        res["timezone"] = [_hit(n, f"clock time '{m.group(0)}' has no time zone", "append the zone from the source (14:30 UTC); the source gives none: write 'zone not given'")
                           for n, ln in prose for m in CLOCK.finditer(ln) if not ZONE.search(ln[m.end():m.end() + 30]) and not ZONE_UNKNOWN.search(ln)]
    if "structure" in res:
        res["structure"] = [_hit(n, p, "see references/leadership-status-update.md") for n, p in status_update_lint.lint(text)]
    if "verified" in res and not any(VERIFY.search(ln) and RESULT.search(ln) for _, ln in prose):
        res["verified"].append(_hit(None, "no verification line with a result", "add `**Verified:** ✅ <check → result>  ⏳ <not verified; owner, date>`"))
    if "command" in res and not re.search(r"`[^`\n]+`|```", text):
        res["command"].append(_hit(None, "no runnable command", "add the one command that shows the result, in backticks"))
    if source is not None:
        seen, known = _figures(source, True), source.lower()
        for n, ln in prose:
            if ESTIMATE.search(ln):
                continue
            bad = sorted(f for f in _figures(ln) - seen if not re.fullmatch(r"20\d\d", f))
            if bad:
                res["grounded"].append(_hit(n, "figure not in the source: " + ", ".join(bad), "delete it, or mark it as estimated with its basis (~N, from X)"))
            for key, rx in CLAIMS:
                if rx.search(ln) and key not in known:
                    res["grounded"].append(_hit(n, f"'{rx.search(ln).group(0)}' is not in the source", "keep only what the author stated; name the options and who decides"))
    order = ("lead", "sections", "table", "numeric", "dri", "links", "budget", "length", "dates", "numbers", "ask", "markers", "verified", "structure", "command", "vocab", "timezone", "filler",
             "placeholder", "vague", "grounded", "hedge")
    rules = [{"rule": r, "ok": not res[r], "advisory": r in ADVISORY, "hits": res[r]} for r in order if r in res]
    return {"kind": kind, "ok": all(r["ok"] or r["advisory"] for r in rules), "score": [sum(r["ok"] for r in rules), len(rules)],
            "words": words, "lines": len(prose), "budget": [max_words, max_lines], "rules": rules}


def render(res):
    """Human-readable report: one FAIL/WARN line per hit with its exact fix, then a score line."""
    out = []
    for r in res["rules"]:
        for h in r["hits"]:
            out.append(f"{'WARN' if r['advisory'] else 'FAIL'} {r['rule']} {'L%d' % h['line'] if h['line'] else '-'}: {h['problem']}. Fix: {h['fix']}")
    p, t = res["score"]
    out.append(f"comms_lint {res['kind']}: {p}/{t} rules pass, {res['words']}/{res['budget'][0]} words, "
               f"{res['lines']}/{res['budget'][1]} lines: {'ok' if res['ok'] else 'BELOW BAR'}")
    return "\n".join(out)


def main(argv):
    ap = argparse.ArgumentParser(prog="comms_lint.py")
    ap.add_argument("--kind")
    ap.add_argument("--file", default="-")
    ap.add_argument("--source")
    ap.add_argument("--range", help="git range BASE..HEAD whose changed files audit-pr must name under 'Changes by area'")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list", action="store_true")
    try:
        a = ap.parse_args(argv[1:])
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        kinds = load_kinds()
        if a.list:
            print("\n".join(f"{k}\t{w}\t{ln}\t{','.join(c)}" for k, (w, ln, c) in kinds.items()))
            return 0
        if a.kind not in kinds:
            print(f"usage: comms_lint.py --kind {{{','.join(kinds)}}} [--file F] [--source S] [--range R] [--json]", file=sys.stderr)
            return 2
        text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
        src = open(a.source, encoding="utf-8").read() if a.source else None
    except (OSError, UnicodeError, ValueError) as e:
        print(f"comms_lint: unreadable input ({type(e).__name__})", file=sys.stderr)
        return 2
    try:
        files = changed_files(a.range) if a.range else None
    except (OSError, ValueError) as e:  # a range git cannot read must not pass as "nothing changed"
        print(f"comms_lint: cannot read --range ({e})", file=sys.stderr)
        return 2
    res = lint(a.kind, text, src, files)
    print(json.dumps(res, indent=1, ensure_ascii=False) if a.json else render(res))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
