#!/usr/bin/env python3
"""Generate docs/scoreboard.md: one row per (Perun skill or feature x rival), read only from committed results.

  scoreboard.py           write docs/scoreboard.md
  scoreboard.py --check   exit 1 unless docs/scoreboard.md equals the regenerated page (CI gate)

Sources, all committed: the head-to-head table, outcome checks, H8 and H14 in docs/perun-vs-rivals.md,
docs/review-cost-per-recall.tsv, the token-voice bench (docs/bench/token-voice-1026), and every rival row of
docs/capability-matrix.md.

Verdicts are computed from a published interval, never read from prose. Win rates test against 0.5, paired
differences against 0: lower bound above the null = win, upper bound below = loss, interval inside null +/- 0.10 =
tie, anything else = "not a win" (the interval is too wide to call a tie). Two independent intervals (H8) are
compared by non-overlap. Equal point estimates with no interval are reported as such and are not ties. A figure a
source does not publish prints UNMEASURED; nothing is estimated. Ratios are Perun divided by the rival.

Every row carries proofs: each cited path must exist and each number must appear as a string in one file under it
(a bench dir) or in the cited file. A failed proof aborts generation and --check, so a row cannot cite a directory
that does not hold its number. The match is textual or by rounding (0.463 and 0.232 match 0.4633 and 0.231884), not a
recomputation.
"""
import csv
import functools
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
PAGE = DOCS / "scoreboard.md"
VS = (DOCS / "perun-vs-rivals.md").read_text()
U = "UNMEASURED"
MARGIN = 0.10
CI = r"(-?\d?\.\d+) \[([+-]?\d?\.\d+), ([+-]?\d?\.\d+)\]"
DIFF = r"([+-]\d\.\d+) \[([+-]\d\.\d+), ([+-]\d\.\d+)\]"
HEAD = {"growth-analytics": ("Round 4 edit", "growth-r4-1018")}  # newest shipped edit is not the cell's first interval
# Capability-matrix rows whose measurement is a newer, fuller row elsewhere on this page.
SUPERSEDED = {("1", "pr-review-toolkit"), ("1", "/code-review"), ("1", "obra"), ("2", "phuryn"), ("3", "obra"),
              ("7", "gstack"), ("9", "promptfoo"), ("9", "humanizer"), ("16", "marketingskills"),
              ("16", "deanpeters"), ("17", "cc-safety-net"), ("17", "hooks-mastery"), ("5", "caveman"), ("5", "ponytail")}
REVIEW_RIVALS = {"Anthropic toolkit code-reviewer": "Anthropic pr-review-toolkit", "/code-review": "Claude Code /code-review",
                 "obra requesting-code-review": "obra/superpowers (requesting-code-review)",
                 "wshobson code-reviewer": "wshobson code-reviewer"}
TV = "docs/bench/token-voice-1026"
EQ = "equal point estimate, no CI"
NV = "measured, no verdict rule"
# Verdicts that are not clean wins: counted apart, never in a win total.
LABEL = {"deviation win": "win (outcome, rule deviation: simulated readers, shipped over a frozen-rule REVERT)",
         "narrative win": "win (outcome, narrative only: no committed result file)",
         "unconfirmed win": "win (preference proxy), not confirmed as outcome"}


def verdict(lo, hi, null=0.5):
    if lo > null:
        return "win"
    if hi < null:
        return "loss"
    return "tie" if lo >= null - MARGIN and hi <= null + MARGIN else "not a win"


@functools.lru_cache(maxsize=None)
def _files(p):
    return tuple(sorted(f for f in p.rglob("*") if f.is_file() and f.stat().st_size < 8_000_000)) if p.is_dir() else (p,)


@functools.lru_cache(maxsize=None)
def _text(f):
    return f.read_text(errors="ignore")


@functools.lru_cache(maxsize=None)
def _rounded(f, d):
    return {round(abs(float(t)), d) for t in re.findall(r"\d*\.\d+", _text(f))}


def _has(f, n):
    """The needle as written, or any decimal in the file that rounds to it (0.232 matches 0.231884)."""
    return n in _text(f) or ("." in n and round(float(n), len(n.split(".")[1])) in _rounded(f, len(n.split(".")[1])))


def holds(path, needles, root=REPO):
    """True when `path` exists and one file under it (or it, if a file) holds every needle number."""
    p = root / path
    return p.exists() and any(all(_has(f, n) for n in needles) for f in _files(p))


def verify(rows, root=REPO):
    """Exit non-zero when a row cites a path that is missing or does not hold the row's numbers."""
    for r in rows:
        for path, needles in r["proofs"]:
            if not holds(path, needles, root):
                sys.exit(f"scoreboard: row '{r['feature']} x {r['rival']}' cites {path}, which is missing or does not hold {needles}")


def row(feature, rival, kind, v, detail="", cost=U, tok=U, date="", proofs=(), caveat="", q=None):
    suffix = {"pref": " (preference proxy)", "outcome": " (outcome)"}.get(kind, "") if v in ("win", "tie", "loss", "not a win") else ""
    q = q or (U if v == U else f"{LABEL.get(v, v + suffix)}: {detail}" + (f". Caveat: {caveat}." if caveat else ""))
    return {"feature": feature, "rival": rival, "kind": kind, "v": v, "q": q, "cost": cost, "tok": tok, "date": date or U,
            "proofs": list(proofs), "src": ", ".join(f"`{p}`" for p, _ in proofs)}


def note(text, phrase, display):
    assert phrase in text, f"caveat source moved: {phrase}"
    return display


def date(text, *dirs):
    """ISO date from a bench dir's trailing MMDD, the year taken from a dated mention of it in the doc; else UNMEASURED."""
    for d in dirs:
        m = re.search(r"-(\d\d)(\d\d)$", d)
        y = m and re.search(rf"(20\d\d)-{m[1]}-{m[2]}", VS)
        if y:
            return f"{y[1]}-{m[1]}-{m[2]}"
    m = re.search(r"20\d\d-\d\d-\d\d", text)
    return m[0] if m else U


def ratio(a, b):
    return f"{a / b:.2f}x" if a is not None and b else U


def num(s):
    return float(s.replace(",", ""))


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split(" | ")]


def table(title_re, text):
    """Rows (cell lists) of the first markdown table after a heading matching title_re."""
    m = re.search(title_re, text)
    rows = []
    for l in text[m.end():].split("\n"):
        if l.startswith("|"):
            rows.append(cells(l))
        elif rows:
            break
    return rows[2:]


def paragraph(start):
    return next(l for l in VS.split("\n") if l.startswith(start))


def h2h_rows():
    """Head-to-head table at the top of perun-vs-rivals.md; the last row per (skill, rival) is the headline."""
    lines = VS.split("\n")
    i = next(k for k, l in enumerate(lines) if l.startswith("| Skill | Rival"))
    pairs, rival = {}, ""
    for l in lines[i + 2:]:
        if not l.startswith("|"):
            break
        c = cells(l)
        assert len(c) == 7, l[:80]
        rival = rival if c[1] == "same" else re.split(r" \(the round", c[1])[0]
        pairs.setdefault((c[0], rival), []).append(c)
    out = []
    for (skill, rival), cs in pairs.items():
        c = cs[-1]
        dirs = re.findall(r"`([\w-]+-\d{4})`", c[2])
        cell, anchor = c[5], 0
        if skill in HEAD:
            a, d = HEAD[skill]
            assert a in cell and d in dirs, f"{skill}: headline anchor moved"
            anchor, dirs = cell.index(a), [d]
        m = re.search(CI, cell[anchor:])
        if not m:
            out.append(row(f"{skill} (head-to-head)", rival, "pref", U, proofs=[("docs/perun-vs-rivals.md", [])]))
            continue
        wtl = re.search(r"\((\d+)(?: W)? / (\d+)(?: T)? / (\d+)(?: L)?[;)]", cell[anchor + m.start():])
        n = sum(map(int, wtl.groups())) if wtl else c[4].split(";")[0]
        lo, hi = float(m[2]), float(m[3])
        v = verdict(lo, hi)
        cav = []
        if v == "win" and lo - 0.5 < 0.02:
            cav.append(f"narrow, lower bound {m[2]} is within 0.02 of 0.5")
        ties = re.search(r"(\d+) of (\d+) (?:tickets|scenarios) are 0\.5 under strict agreement", c[6])
        if ties:
            cav.append(f"{ties[1]} of {ties[2]} items tied under strict agreement")
        for e in cs[:-1]:
            em = re.search(CI, e[5])
            if em and float(em[2]) > 0.5 and v != "win":
                cav.append(f"an earlier run ({re.findall(r'`([\w-]+-\d{4})`', e[2])[0]}) won {em[1]} [{em[2]}, {em[3]}] and did not replicate")
        needles = [m[1], m[2], m[3]]
        d0 = next((d for d in dirs if holds(f"docs/bench/{d}", needles)), None)
        if d0 is None:
            sys.exit(f"scoreboard: no cited bench dir of {skill} holds {needles}: {dirs}")
        t = re.search(r"Perun ([\d,]+) vs rival ([\d,]+)", c[6])
        out.append(row(f"{skill} (head-to-head)", rival, "pref", v, f"win rate {m[1]} [{m[2]}, {m[3]}], n={n}, blind judge",
                       tok=ratio(*(num(x) for x in t.groups())) if t else U, date=date(c[6], d0),
                       proofs=[("docs/perun-vs-rivals.md", needles), (f"docs/bench/{d0}", needles)], caveat="; ".join(cav)))
    return out


def outcome_rows(h2h):
    """Outcome checks that follow the head-to-head table; a proxy row for the same pair is marked superseded."""
    pc, ps = paragraph("Outcome check on communication-structure"), paragraph("Outcome check on product-output-safety")
    for h in h2h:
        if h["feature"] == "communication-structure (head-to-head)" and h["rival"] == "humanizer":
            v, rest = h["q"].split(" (preference proxy): ", 1)
            h["v"], h["kind"] = "superseded", "none"
            h["q"] = f"superseded by the outcome rows below (the preference proxy said {v}: {rest.split('. Caveat')[0]})"
    note(pc, "The rule still returned REVERT", "")
    note(pc, "Owner decision (2026-10-19): ship E4 with that deviation disclosed", "")
    out = []
    for feat, rival, para, pat, d, label in (
        ("communication-structure (outcome, reader accuracy)", "humanizer", pc, r"shipped minus humanizer " + DIFF, "comms-outcome-1019",
         "pre-E4 skill text, n=30 scenarios, simulated readers"),
        ("communication-structure (outcome, reader accuracy)", "humanizer", pc, r"beats humanizer on reader accuracy, " + DIFF,
         "comms-e4-confirm-1019", "shipped E4 text, n=500 scenarios, simulated readers; E4 shipped with a disclosed deviation from the frozen rule"),
        ("product-output-safety (outcome, flagged-harm recall)", "promptfoo redteam-setup (run without its tools)", ps,
         r"shipped minus rival " + DIFF, "safety-outcome-1019", "n=84 synthetic specs, one answering model, scored on the skill's own harm inventory")):
        m = re.search(pat, para)
        needles = [x.lstrip("+-") for x in m.groups()]
        v = verdict(float(m[2]), float(m[3]), 0)
        out.append(row(feat, rival, "outcome", "deviation win" if v == "win" and d == "comms-e4-confirm-1019" else v,
                       f"Perun minus rival {m[1]} [{m[2]}, {m[3]}]; {label}", date=date(para, d),
                       proofs=[("docs/perun-vs-rivals.md", needles), (f"docs/bench/{d}", needles)]))
    for h in h2h:  # a preference win that its own outcome check did not confirm
        o = next((r for r in out if r["feature"].startswith(h["feature"].split(" (")[0] + " (outcome")), None)
        if o and h["v"] == "win" and o["v"] != "win":
            h["v"] = "unconfirmed win"
            h["q"] = h["q"].replace("win (preference proxy)", f"win (preference proxy), not confirmed as outcome ({o['proofs'][1][0].split('/')[-1]} {o['v']})", 1)
    return out


def review_rows():
    rows = list(csv.DictReader((DOCS / "review-cost-per-recall.tsv").open(), delimiter="\t"))
    out = []
    for s in dict.fromkeys(r["set"] for r in rows):
        grp = {r["arm"]: r for r in rows if r["set"] == s}
        p = next((r for a, r in grp.items() if a.startswith("Perun")), None)
        for arm, name in REVIEW_RIVALS.items():
            r = grp.get(arm)
            if not (p and r):
                continue
            pr, rr = float(p["recall"]), float(r["recall"])
            if pr != rr:
                continue  # only equal point estimates are published here; a gap without an interval is not scored
            needles = [p["recall"], r["recall"], f"${float(p['usd_case']):.3f}", f"${float(r['usd_case']):.3f}"]
            out.append(row("Code review (recall per case)", name, "outcome", EQ,
                           f"recall {pr} vs {rr}, n={p['n']}; not a tie, because no interval is published",
                           cost=ratio(float(p["usd_case"]), float(r["usd_case"])), date=date(s),
                           proofs=[("docs/review-cost-per-recall.tsv", []), (p["source"], needles)],
                           caveat="aggregate numbers only, per-case data not committed"))
    return out


def h8_rows():
    sec = VS[VS.index("### H8."):VS.index("### H9.")]
    t = {c[0]: c[1] for c in table(r"### H8\.[^\n]*\n", VS)}
    cav = note(sec, "so the lead over the rivals is indicative", "no committed result file, narrative only; 32-string own corpus, so the lead is indicative only; best-effort string check, not a security boundary")
    p = re.match(r"(\d+) \[([.\d]+), ([.\d]+)\]", t["Perun destructive guard (1.580.0)"])
    out = []
    for name, rival in (("claude-code-safety-net", "kenryu42/cc-safety-net"), ("hooks-mastery", "disler/claude-code-hooks-mastery")):
        r = re.match(r"(\d+) \[([.\d]+), ([.\d]+)\]", t[name])
        v = "narrative win" if float(p[2]) > float(r[3]) else "loss" if float(p[3]) < float(r[2]) else "not a win"
        out.append(row("Destructive-command guard (blocked of 32 dangerous)", rival, "outcome", v,
                       f"{p[1]} [{p[2]}, {p[3]}] vs {r[1]} [{r[2]}, {r[3]}], n=32, Wilson intervals compared by overlap",
                       proofs=[("docs/perun-vs-rivals.md", [p[2], r[3]])], caveat=cav))
    return out


def h14_rows():
    sec = VS[VS.index("### H14."):VS.index("### H15.")]
    d = date(sec.split("\n")[0], "hidden-test-r2-1021")
    cav = note(sec, "single-module tickets written by the Perun side", "one model, one turn, no tools; single-module tickets written by the Perun side")
    cav += "; " + note(sec, "this table is the exploratory pilot", "exploratory pilot") + "; " + note(sec, "preregistered fresh-seed check; REVERT", "preregistered recheck REVERT")
    tok = {}
    for split in ("Easy", "Hard"):
        for c in table(rf"{split} split \(\d+ tickets\):\n\n", sec):
            tok[split, c[0]] = num(c[2]) + num(c[3])
    pair = {c[0]: c for c in table(r"\| A minus B \(paired\)[^\n]*\n", sec)}
    out = []
    for arm, name in (("superpowers", "obra/superpowers (TDD, debugging)"), ("agent-skills", "addyosmani/agent-skills (TDD, debugging)")):
        for i, split in enumerate(("Easy", "Hard"), 1):
            m = re.match(DIFF, pair[f"Perun - {arm}"][i])
            needles = [x.lstrip("+-") for x in m.groups()]
            sub = next((p for p in ("pilot", "confirm") if holds(f"docs/bench/hidden-test-r2-1021/{p}", needles)), "pilot")
            out.append(row("Bug-fix outcome, Perun text as system prompt (hidden-test pass rate)", f"{name}, {split.lower()} split", "outcome",
                           verdict(float(m[2]), float(m[3]), 0), f"Perun minus rival {m[1]} [{m[2]}, {m[3]}], paired, {split.lower()} split",
                           tok=ratio(tok[split, "Perun"], tok[split, arm]), date=d, caveat=cav,
                           proofs=[("docs/perun-vs-rivals.md", needles), (f"docs/bench/hidden-test-r2-1021/{sub}", needles)]))
    return out


# (anchor in the bench README, caveat shown on the rows): a caveat the README drops fails generation.
TV_CAVEATS = (
    ("default Perun is not measured here", "the opt-in `--with-terse-replies` reply budget plus the zero-chat rule of the lane preamble (the lane default); the default install applies no cap, so default Perun is not measured"),
    ("it is a hard length cap, so a token win against uncapped arms is expected", "a hard length cap, so a token win against uncapped arms is expected, not a general voice or reasoning improvement"),
    ("One model (Haiku 5.5, thinking disabled), one task family (small Python bug fixes, no tools)", "one model (Haiku 5.5, thinking disabled), one task family (small Python bug fixes, no tools), no claim about agentic sessions, other models or long outputs"),
    ("No multiplicity correction across the five pairs", "no multiplicity correction across the five pairs; non-inferior at the -0.05 margin, not proven equal"),
    ("pass rates are near 100%", "pass rates near 100%, so little power to see small regressions"),
    ("Cost is the CLI-reported list cost", "cost is the CLI-reported list cost and includes input tokens"),
    ("Deviation from the preregistration: the frozen run targeted a free PCSS model; budget exhausted (HTTP 429)",
     "deviation from the preregistration: the free model of the frozen run hit HTTP 429, so the arms ran on Haiku 5.5 via the claude CLI (disclosed in ledger.jsonl)"))


def token_voice_rows():
    """The Perun arm (opt-in reply budget plus the lane-default zero-chat rule) against the caveman and ponytail texts on bug-fix tasks. Quality is the paired pass-rate
    interval against 0 (like H14); the per-task median token ratio and the list-cost ratio go in their columns."""
    text = (REPO / TV / "README.md").read_text()
    flat = " ".join(text.split())
    t = {c[0]: c for c in (cells(l) for l in text.split("\n") if l.startswith("|"))}
    cost = json.loads((REPO / TV / "cost.json").read_text())
    when = date((REPO / TV / "ledger.jsonl").read_text(), "token-voice-1026")
    n = re.search(r"(\d+) hidden-test bug-fix tasks x (\d+) samples", flat)
    pony = re.search(r"Ponytail: (\d+) of its (\d+) replies add `test_`/`assert` code the task did not ask for \(0 of (\d+) in every other arm\)", flat)
    assert n and pony, "caveat source moved: token-voice README"
    cav = "; ".join(note(flat, a, d) for a, d in TV_CAVEATS)
    out = []
    for arm, rival in (("caveman (ultra)", "JuliusBrussee/caveman (ultra level)"), ("ponytail", "DietrichGebert/ponytail")):
        key = arm.split()[0]
        _, td, tr, pd, keep = t[f"perun vs {key}"]
        tm, pm = re.fullmatch(r"([+-]?\d+) \(([+-]?\d+) to ([+-]?\d+)\)", td), re.fullmatch(r"([+-]?[\d.]+) \(([+-]?[\d.]+) to ([+-]?[\d.]+)\)", pd)
        assert (float(tm[3]) < 0 and float(pm[2]) > -0.05) == (keep == "win"), f"{key}: published keep rule disagrees with its intervals"
        dec = [x.lstrip("+-") for x in (*pm.groups(), tr)]
        own = f"{pony[1]} of its {pony[2]} replies add test_/assert code the task did not ask for (0 of {pony[3]} in every other arm), which inflates its tokens, so this is not a voice win; " if key == "ponytail" else ""
        out.append(row("Compressed-prose and minimal-code modes (opt-in reply budget plus zero-chat rule, bug-fix tasks)", rival, "outcome", verdict(float(pm[2]), float(pm[3]), 0),
                       f"hidden-test pass rate, Perun minus rival {pm[1]} [{pm[2]}, {pm[3]}], paired over {n[1]} tasks x {n[2]} samples; output tokens per task: "
                       f"median {t['perun'][1]} vs {t[arm][1]}, paired median diff {tm[1]} [{tm[2]}, {tm[3]}], per-task median ratio {tr} (95% CIs); "
                       f"the bench's frozen keep rule (token CI upper bound below 0, pass CI lower bound above -0.05) returns {keep}",
                       cost=ratio(cost["perun"]["cost_usd"], cost[key]["cost_usd"]), tok=f"{tr}x", date=when, caveat=own + cav,
                       proofs=[(f"{TV}/README.md", [x.lstrip("+-") for x in (*tm.groups(), *pm.groups(), tr, t["perun"][1], t[arm][1], n[1])]),
                               (f"{TV}/results.json", dec), (f"{TV}/cost.json", [str(cost["perun"]["cost_usd"]), str(cost[key]["cost_usd"])]),
                               (f"{TV}/ledger.jsonl", [when])]))
    return out


def matrix_rows():
    text, out, sec = (DOCS / "capability-matrix.md").read_text(), [], None
    for l in text.split("\n"):
        h = re.match(r"## (\d+)\. (.*)", l)
        if h:
            sec = h.groups()
        elif sec and l.startswith("| ["):
            c = cells(l)
            name = re.match(r"\[([^\]]+)\]", c[0])[1].replace("`", "")
            if any(sec[0] == s and k in name.lower() for s, k in SUPERSEDED):
                continue
            d = re.sub(r"^Measured:? ", "", re.sub(r"\s+", " ", c[2]))
            unmeasured = c[2].startswith("Not measured")
            out.append(row(sec[1], name, "none", U if unmeasured else NV, proofs=[("docs/capability-matrix.md", [])],
                           q=U if unmeasured else f"{NV} (read the source): {d[:150].rstrip(' ,;.')} ..."))
            out[-1]["src"] = f"`docs/capability-matrix.md` section {sec[0]}"
    return out


def build():
    h2h = h2h_rows()
    rows = h2h + outcome_rows(h2h) + review_rows() + h14_rows() + token_voice_rows() + h8_rows() + matrix_rows()
    verify(rows)
    c = {}
    for r in rows:
        c[r["kind"], r["v"]] = c.get((r["kind"], r["v"]), 0) + 1
    g = lambda k: ", ".join(f"{c.get((k, x), 0)} {x}" for x in ("win", "tie", "loss", "not a win"))  # noqa: E731
    k = lambda *key: c.get(key, 0)  # noqa: E731
    clean = k("outcome", "win")
    head = (
        "# Perun scoreboard\n\nGenerated by `scripts/scoreboard.py` from committed results; do not edit. "
        "`scripts/scoreboard.py --check` fails when this page is stale or a row cites a path that does not hold its number.\n\n"
        f"**{len(rows)} rows. Clean outcome wins: {clean}"
        + (" (Perun has no clean outcome win)" if not clean else "")
        + f". Outcome measures (hidden tests, reader accuracy, answer-key recall): {g('outcome')}, {k('outcome', EQ)} {EQ}; "
        f"apart from those: {k('outcome', 'deviation win')} outcome win with a rule deviation (communication-structure E4, simulated readers, "
        f"shipped over a frozen-rule REVERT) and {k('outcome', 'narrative win')} narrative-only wins (destructive-command guard, no committed "
        f"result file), neither counted as a win. Preference proxy (blind judge): {g('pref')}, {k('pref', 'unconfirmed win')} win not confirmed as "
        f"outcome (product-output-safety), {k('none', 'superseded')} superseded by an outcome row. "
        f"Measured, no verdict rule: {k('none', NV)}. {U}: {sum(n for (_, v), n in c.items() if v == U)}.**\n\n"
        "A verdict is computed from a published interval (rules in the script docstring); a cell with no published figure says "
        f"{U}. Ratios are Perun divided by the rival (below 1.00x means Perun is cheaper). A blind-judge preference win is a proxy, "
        "not an outcome, and a tie needs the whole interval within 0.10 of the null; a wider interval is \"not a win\".\n\n"
        "| Perun skill or feature | Rival | Quality verdict | Cost ratio | Token ratio | Date | Source |\n|---|---|---|---|---|---|---|\n")
    return head + "\n".join(f"| {r['feature']} | {r['rival']} | {r['q']} | {r['cost']} | {r['tok']} | {r['date']} | {r['src']} |" for r in rows) + "\n"


def main(argv):
    page = build()
    if argv == ["--check"]:
        if not PAGE.exists() or PAGE.read_text() != page:
            sys.exit("docs/scoreboard.md is stale: run python3 scripts/scoreboard.py")
    elif argv:
        sys.exit(__doc__)
    else:
        PAGE.write_text(page)


if __name__ == "__main__":
    main(sys.argv[1:])
