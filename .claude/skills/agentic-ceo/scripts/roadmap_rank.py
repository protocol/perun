#!/usr/bin/env python3
"""roadmap_rank.py: deterministic scoring and ranking for the CEO improvement loop. Stdlib only.

Usage:
  roadmap_rank.py INPUT.json [--root DIR] [--strict] [--update FILE]
  roadmap_rank.py ITEMS.csv --context CTX.json [--root DIR] [--strict] [--update FILE]

INPUT.json: {"as_of": "YYYY-MM-DD", "context": {stage, vision, north_star, direction, constraints: each
{"value", "src"}; optional "weights"}, "sources": [str], "items": [...], "adrs": [...]}. A CSV carries only
the items (list fields joined with ';'); CTX.json carries the rest. Field names and rules are in
references/improvement-loop.md. Every violation is listed at once and exits 2.

Prints the report in the loop's fixed order: strategy context, rejected items, ranked roadmap, ADRs,
tracker issues. The same input always gives the same output (no clock, no network).

  score = reach x impact x confidence / effort x stage_weight x vision_factor

Every input is sourced or marked `assumed`; confidence is capped at 0.5 while reach or impact is assumed.
--update FILE replaces the text between <!-- roadmap:begin --> and <!-- roadmap:end --> in FILE.
--strict exits 1 when a top-3 item has no idea-critic verdict or an unresolved REVISE.
--root DIR is where repo-path evidence is resolved (default: the current directory).
Exit: 0 ok, 1 --strict failed, 2 bad input.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import itertools
import json
import os
import re
import sys
from pathlib import Path

STAGES = ("prototype", "mvp", "growth", "mature")  # deep-code-review's STAGE model
# lever -> weight per stage, in STAGES order. Policy defaults, not measurements; a run may override a
# lever with context.weights {"lever": [4 numbers]}. Every report prints the table it used.
W = {
    "learning": (1.5, 1.5, 1.0, 0.75),
    "reliability": (1.0, 1.25, 1.5, 1.5),
    "velocity": (1.25, 1.25, 1.0, 0.75),
    "growth": (0.25, 0.5, 1.5, 0.75),
    "scale": (0.25, 0.5, 1.25, 1.5),
    "cost": (0.5, 0.75, 1.25, 1.5),
    "polish": (0.25, 0.5, 1.0, 1.25),
    "security": (1.5, 1.5, 1.5, 1.5),  # the floor never relaxes: the top weight at every stage
}
VISION = {"aligned": 1.0, "partial": 0.5}  # "misaligned" is a rejection, not a factor
IMPACT = (0.25, 0.5, 1, 2, 3)
CAP = 0.5  # confidence ceiling while reach or impact is assumed
INPUTS = ("reach", "impact", "confidence", "effort")
CTX = ("stage", "vision", "north_star", "direction", "constraints")
ROLES = ("CEO", "CPO", "CTO", "CFO", "CMO", "CISO", "COO")
AREAS = ("architecture", "pipeline", "tooling")
VERDICTS = ("PASS_TO_USER", "REVISE", "HOLD")
BEGIN, END = "<!-- roadmap:begin -->", "<!-- roadmap:end -->"


def assumed(s):
    return str(s).strip().lower().startswith("assumed")


def cell(s):
    return " ".join(str(s).split()).replace("|", "\\|")


def text(v):
    return isinstance(v, str) and bool(v.strip())


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def g(x):
    return f"{x:g}"


def join(v):
    return "; ".join(str(x).rstrip(".") for x in v) if isinstance(v, list) else str(v)


def load(path, ctx_path=None):
    p = Path(path)
    if p.suffix.lower() != ".csv":
        return json.loads(p.read_text(encoding="utf-8"))
    if not ctx_path:
        raise ValueError("a CSV needs --context CTX.json (as_of, context, sources, adrs)")
    with p.open(newline="", encoding="utf-8") as f:
        items = [{k: v.strip() for k, v in r.items() if k and v and v.strip()} for r in csv.DictReader(f)]
    for it in items:
        for k in ("evidence", "merged_from"):
            if k in it:
                it[k] = [x.strip() for x in it[k].split(";") if x.strip()]
        for k in INPUTS:
            try:
                it[k] = float(it[k])
            except (KeyError, ValueError):
                pass  # build() reports a missing or non-numeric input
    data = json.loads(Path(ctx_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("--context must be a JSON object")
    data["items"] = items
    return data


def ev_ok(e, root):
    e = str(e).strip()
    if re.match(r"https?://\S+$", e) or re.match(r"[a-z][a-z0-9-]*:\S", e):
        return True  # a URL, or tag:ref such as issue:#12 or survey:2026-10-16#P1
    p = (root / e.split("#")[0]).resolve()
    return bool(e) and p.exists() and root.resolve() in (p, *p.parents)  # a repo path, not an outside one


def build(data, root):
    """Validate, score and rank. Returns (result, errors); result is None when there are errors."""
    errs = []
    if not isinstance(data, dict) or not isinstance(data.get("context"), dict) or not isinstance(data.get("items"), list):
        return None, ["input must be an object with context{} and items[]"]
    ctx = data["context"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(data.get("as_of", ""))):
        errs.append("as_of must be YYYY-MM-DD (the report carries no clock)")
    for k in CTX:
        v = ctx.get(k)
        if not (isinstance(v, dict) and text(v.get("value")) and text(v.get("src"))):
            errs.append(f"context.{k} needs value and src; if the docs are silent, state the assumption with src 'assumed: ...'")
    stage = ctx["stage"].get("value") if isinstance(ctx.get("stage"), dict) else None
    if stage not in STAGES:
        errs.append(f"context.stage.value must be one of {', '.join(STAGES)}")
    w, over, applied = dict(W), ctx.get("weights") or {}, []
    for k, v in (over.items() if isinstance(over, dict) else [("weights", None)]):
        if k in W and isinstance(v, list) and len(v) == 4 and all(num(x) and x > 0 for x in v):
            w[k] = tuple(v)
            applied.append(k)
        else:
            errs.append(f"context.weights.{k}: a known lever and 4 positive numbers are required")
    si = STAGES.index(stage) if stage in STAGES else 0

    ids, rejected, flight, cand = set(), [], [], []
    for n, it in enumerate(data["items"]):
        i = it.get("id") if isinstance(it, dict) else None
        if not (isinstance(i, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", i)):
            errs.append(f"items[{n}]: id must be a lowercase slug")
            continue
        if i in ids:
            errs.append(f"{i}: duplicate id; merge the two returns (record merged_from) or rename one")
            continue
        ids.add(i)

        def bad(m, i=i):
            errs.append(f"{i}: {m}")

        if not text(it.get("title")):
            bad("title is required")
        if it.get("reject") is not None or it.get("vision") == "misaligned":
            by_ceo = it.get("reject") is not None
            why = it["reject"] if by_ceo else it.get("vision_reason")
            if not text(why):
                bad("a rejection needs a stated reason (reject, or vision_reason when vision is misaligned)")
            rejected.append((it, "CEO decision" if by_ceo else "vision: misaligned", why))
            continue
        ev = it.get("evidence")
        if not (isinstance(ev, list) and ev):
            bad("evidence needs at least one link, repo path or tag:ref")
        else:
            for e in ev:
                if not ev_ok(e, root):
                    bad(f"evidence not found: {e}")
        if not (text(it.get("metric")) and re.search(r"\d", it["metric"])):
            bad("metric must be measurable: name a baseline or target number")
        if not text(it.get("risks")):
            bad("risks is required")
        status = it.get("status", "open")
        if status == "in_flight":
            flight.append(it)
            continue
        if status != "open":
            bad("status must be open or in_flight")
            continue
        if it.get("lever") not in w:
            bad(f"lever must be one of {', '.join(w)}")
        for k, ok in (("reach", lambda v: 1 <= v <= 5), ("impact", lambda v: v in IMPACT),
                      ("confidence", lambda v: 0 < v <= 1), ("effort", lambda v: v > 0)):
            if not (num(it.get(k)) and ok(it[k])):
                bad(f"{k} is missing or out of range (reach 1-5, impact {'|'.join(map(str, IMPACT))}, confidence 0-1, effort > 0)")
            if not text(it.get(k + "_src")):
                bad(f"{k}_src is required: a link or 'assumed: why'")
        if it.get("vision") not in VISION:
            bad("vision must be aligned, partial or misaligned")
        for k in ("vision_reason", "where", "done_when", "verify"):
            if not text(it.get(k)):
                bad(f"{k} is required")
        if "role" in it and it["role"] not in ROLES:
            bad(f"role must be one of {', '.join(ROLES)}")
        c = it.get("critic")
        if c is not None:
            if not (isinstance(c, dict) and c.get("verdict") in VERDICTS and c.get("independence") in ("inline", "independent")):
                bad("critic needs verdict (PASS_TO_USER|REVISE|HOLD) and independence (inline|independent); check the full verdict with idea-critic's validate_verdict.py")
            elif c["verdict"] == "PASS_TO_USER" and not text(c.get("strongest_attack_survived")):
                bad("critic PASS_TO_USER needs strongest_attack_survived")
            elif c["verdict"] == "HOLD" and not text(c.get("dissent_ledger")):
                bad("critic HOLD needs dissent_ledger (the rejection reason)")
        cand.append(it)
    if errs:
        return None, errs

    ranked = []
    for it in cand:
        c = it.get("critic") or {}
        if c.get("verdict") == "HOLD":
            rejected.append((it, "idea-critic: HOLD", c["dissent_ledger"]))
            continue
        conf = min(it["confidence"], CAP) if assumed(it["reach_src"]) or assumed(it["impact_src"]) else it["confidence"]
        sw, vf = w[it["lever"]][si], VISION[it["vision"]]
        ranked.append({"it": it, "conf": conf, "sw": sw, "vf": vf,
                       "s": it["reach"] * it["impact"] * conf / it["effort"] * sw * vf})
    ranked.sort(key=lambda r: (-round(r["s"], 6), r["it"]["effort"], r["it"]["id"]))

    live = {r["it"]["id"] for r in ranked} | {f["id"] for f in flight}
    adrs, seen = [], set()
    for n, a in enumerate(data.get("adrs") or []):
        if not isinstance(a, dict):
            errs.append(f"adrs[{n}]: not an object")
            continue
        tag = f"adr {a.get('id', n)}"
        if a.get("id") in seen:
            errs.append(f"{tag}: duplicate id")
        seen.add(a.get("id"))
        if a.get("item") not in live:
            errs.append(f"{tag}: item must name a ranked or in-flight item (ADRs serve accepted items)")
        if a.get("area") not in AREAS:
            errs.append(f"{tag}: area must be one of {', '.join(AREAS)}")
        o = a.get("options")
        if not (isinstance(o, list) and len(o) >= 2 and all(isinstance(x, dict) and text(x.get("name")) and text(x.get("tradeoffs")) for x in o)):
            errs.append(f"{tag}: options need at least 2 entries with name and tradeoffs (do nothing is an option)")
        if not (text(a.get("decision")) and a["decision"].startswith("We will")):
            errs.append(f"{tag}: decision must be a sentence starting 'We will'")
        for k in ("id", "title", "context", "consequences", "reversal_cost"):
            if not text(a.get(k)):
                errs.append(f"{tag}: {k} is required")
        adrs.append(a)
    if errs:
        return None, errs

    titles = [(x["id"], x["title"].lower()) for x in data["items"]]
    return {
        "ranked": ranked, "rejected": rejected, "flight": flight, "adrs": adrs, "w": w, "over": applied, "si": si, "stage": stage,
        "dups": [(p, q) for (p, a), (q, b) in itertools.combinations(titles, 2)
                 if difflib.SequenceMatcher(None, a, b).ratio() >= 0.85],
        "missing": [r["it"]["id"] for r in ranked[:3] if not r["it"].get("critic")],
        "unresolved": [r["it"]["id"] for r in ranked if (r["it"].get("critic") or {}).get("verdict") == "REVISE"],
    }, []


def render(data, r, base=""):
    """Markdown report. base is prefixed to repo-path evidence so links resolve from the file it lands in."""
    ctx, out, stage = data["context"], [], r["stage"]
    P = out.append

    def ev(it):  # repo paths become links labelled by file name; URLs and tag:ref stay text
        def link(e):
            name = e.rsplit("/", 1)[-1]
            return e if re.match(r"[a-z][a-z0-9-]*:\S", e) else f"[{name if len(name) <= 40 else name[:39] + '…'}]({base}{e})"
        return cell("; ".join(link(str(e).strip()) for e in it["evidence"]))

    parts = [f"Stage `{stage}`" + (" (assumed)." if assumed(ctx["stage"]["src"]) else "."),
             f"{len(r['ranked'])} open items ranked, {len(r['rejected'])} rejected, {len(r['flight'])} in flight."]
    if r["ranked"]:
        parts.append("Top: " + ", ".join(f"`{x['it']['id']}` {x['s']:.2f}" for x in r["ranked"][:3]) + ".")
        free = next((x["it"]["id"] for x in r["ranked"] if not x["it"].get("gate")), None)
        parts.append(f"Start now (highest-ranked item with no gate): `{free}`." if free else "Every ranked item is gated.")
        na = sum(assumed(x["it"]["reach_src"]) for x in r["ranked"])
        if na:
            parts.append("Every reach input is assumed, so read the order as a hypothesis." if na == len(r["ranked"])
                         else f"{na} of {len(r['ranked'])} reach inputs are assumed.")
    else:
        parts.append("No open item survived the rejection rules.")
    P("**BLUF.** " + " ".join(parts) + "\n")
    P("## 1. Strategy context\n")
    P(f"As of {data['as_of']}. A source that starts with **assumed** is an explicit assumption, not a repo fact.\n")
    P("| Field | Value | Source |\n|---|---|---|")
    for k in CTX:
        s = re.sub(r"^assumed", "**assumed**", cell(ctx[k]["src"]), flags=re.I)
        P(f"| {k.replace('_', ' ')} | {cell(ctx[k]['value'])} | {s} |")
    ask = [k.replace("_", " ") for k in CTX if assumed(ctx[k]["src"])]
    if ask:
        P(f"\nOwner question (one batch): confirm or correct the assumed {', '.join(ask)}. "
          "The run continues on the assumption; a correction re-runs this script.")
    if data.get("sources"):
        P("\nEvidence base (a source that was absent or unreadable is listed as such, never skipped):\n")
        out.extend(f"- {s}" for s in data["sources"])

    P("\n## 2. Rejected items\n")
    if r["rejected"]:
        P("| Item | Rule | Reason |\n|---|---|---|")
        for it, rule, why in r["rejected"]:
            P(f"| `{it['id']}` {cell(it['title'])} | {rule} | {cell(why)} |")
    else:
        P("None.")

    P("\n## 3. Ranked roadmap\n")
    P("Score = reach × impact × confidence ÷ effort × stage weight × vision factor. Every input is sourced or "
      "`assumed`; the score orders the list, it does not prove anything.\n")
    P("- reach 1-5: share of our own users or runs touched, 5 = every one (never a market size)")
    P("- impact 0.25, 0.5, 1, 2 or 3: minimal, low, medium, high or massive effect on the north star")
    P(f"- confidence 0-1, capped at {CAP:g} while reach or impact is `assumed`")
    P("- effort: lane-days, above 0")
    P(f"- stage weight: lever × stage from the table below; the active stage is `{stage}`")
    P("- vision factor: aligned 1.0, partial 0.5; a misaligned item is rejected in section 2")
    P("- equal scores are ordered by lower effort, then id\n")
    P("| lever | " + " | ".join(f"{s} (active)" if s == stage else s for s in STAGES) + " |\n|---|---|---|---|---|")
    for lv, row in r["w"].items():
        P(f"| {lv}{' (override)' if lv in r['over'] else ''} | "
          + " | ".join(f"**{g(x)}**" if j == r["si"] else g(x) for j, x in enumerate(row)) + " |")
    if r["ranked"]:
        P("\n| # | Item | Lane, lever | Score | Success metric | Evidence | Gate |\n|---|---|---|---|---|---|---|")
        for n, x in enumerate(r["ranked"], 1):
            it = x["it"]
            P(f"| {n} | `{it['id']}` {cell(it['title'])} | {it.get('role', '-')}, {it['lever']} | {x['s']:.2f} | "
              f"{cell(it['metric'])} | {ev(it)} | {cell(it.get('gate', '-'))} |")
        P("\nScore inputs:\n")
        P("| # | reach | impact | confidence used | effort | stage × | vision × | score | assumed (R reach, I impact, C confidence, E effort) |\n|---|---|---|---|---|---|---|---|---|")
        for n, x in enumerate(r["ranked"], 1):
            it = x["it"]
            capd = f" (typed {g(it['confidence'])})" if x["conf"] != it["confidence"] else ""
            a = " ".join(k[0].upper() for k in INPUTS if assumed(it[k + "_src"])) or "none"
            P(f"| {n} | {g(it['reach'])} | {g(it['impact'])} | {g(x['conf'])}{capd} | {g(it['effort'])} | "
              f"{g(x['sw'])} | {g(x['vf'])} | {x['s']:.2f} | {a} |")
    else:
        P("\nNo open item survived the rejection rules.")
    if r["flight"]:
        P("\n### Already in flight (listed, not re-ranked)\n")
        P("| Item | Evidence | Metric to check when it lands |\n|---|---|---|")
        for it in r["flight"]:
            P(f"| `{it['id']}` {cell(it['title'])} | {ev(it)} | {cell(it['metric'])} |")
    P("\n### Top 3 attacked by idea-critic\n")
    for n, x in enumerate(r["ranked"][:3], 1):
        it, c = x["it"], x["it"].get("critic")
        if not c:
            P(f"- {n}. `{it['id']}`: **UNVERIFIED**, idea-critic has not run on this item.")
        else:
            P(f"- {n}. `{it['id']}`: **{c['verdict']}** ({c['independence']}). "
              f"Strongest attack survived: {cell(c.get('strongest_attack_survived', '-'))} "
              f"Kill criteria: {cell(join(c.get('kill_criteria', '-')))} Remaining risk: {cell(c.get('remaining_risk', '-'))}")
    if r["unresolved"]:
        P("\nUnresolved REVISE (not a pass): " + ", ".join(f"`{i}`" for i in r["unresolved"]) + ".")
    P(f"\nDedup check: {len(data['items'])} items, near-duplicate titles (similarity 0.85 or more): "
      + ("; ".join(f"{a} ~ {b}" for a, b in r["dups"]) or "none") + ".")

    P("\n## 4. Technical-direction decisions (ADRs)\n")
    if not r["adrs"]:
        P("None.")
    for a in r["adrs"]:
        P(f"### {a['id']}: {a['title']} ({a['area']}), serves `{a['item']}`\n")
        P(f"- Status: {a.get('status', 'proposed')}")
        P(f"- Context: {cell(a['context'])}")
        P("- Options: " + " ".join(f"({chr(65 + n)}) **{cell(o['name'])}**: {cell(o['tradeoffs'])}" for n, o in enumerate(a["options"])))
        P(f"- Decision: {cell(a['decision'])}")
        P(f"- Consequences: {cell(a['consequences'])}")
        P(f"- Reversal cost: {cell(a['reversal_cost'])}\n")

    P("\n## 5. Tracker-ready issues\n")
    P("Priority is rank-derived (ranks 1-3 P1, 4-6 P2, the rest P3); P0 is a human call and is never assigned here. "
      "Issues are drafted for P1 and P2 only; a P3 item stays in the table until it is promoted.\n")
    for n, x in enumerate(r["ranked"][:6], 1):
        it = x["it"]
        P(f"### {'P1' if n <= 3 else 'P2'}: {it['title']}\n")
        P(f"- Labels: `{it['lever']}`" + (f", `{it['role']}`" if "role" in it else "") + f", `stage:{stage}`")
        P(f"- Where: {cell(it['where'])}")
        P(f"- Done when: {cell(it['done_when'])}")
        P(f"- Verify: {cell(it['verify'])}")
        P(f"- Why: {cell(it['vision_reason'])} (vision: {it['vision']})")
        P(f"- Success metric: {cell(it['metric'])}")
        P(f"- Evidence: {ev(it)}")
        P(f"- Risks: {cell(it['risks'])}")
        if it.get("gate"):
            P(f"- Gate: {cell(it['gate'])}")
        if it.get("merged_from"):
            P(f"- Merged from: {cell(join(it['merged_from']))}")
        P(f"- Score: {x['s']:.2f} = {g(it['reach'])} × {g(it['impact'])} × {g(x['conf'])} ÷ {g(it['effort'])} × "
          f"{g(x['sw'])} × {g(x['vf'])} (rank {n} of {len(r['ranked'])})\n")
    if r["ranked"][6:]:
        P("P3, no issue drafted until promoted: " + ", ".join(f"`{x['it']['id']}`" for x in r["ranked"][6:]) + ".\n")
    P("_Generated by `roadmap_rank.py` from the input JSON: edit the input and re-run, never this text._")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input")
    ap.add_argument("--context")
    ap.add_argument("--root", default=".")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--update")
    a = ap.parse_args(argv)
    try:
        data = load(a.input, a.context)
    except (OSError, ValueError) as e:
        print(f"roadmap_rank: cannot read input: {e}", file=sys.stderr)
        return 2
    r, errs = build(data, Path(a.root))
    if errs:
        print("roadmap_rank: bad input:\n" + "\n".join("  - " + e for e in errs), file=sys.stderr)
        return 2
    f = Path(a.update) if a.update else None
    body = render(data, r, Path(os.path.relpath(Path(a.root).resolve(), f.resolve().parent)).as_posix() + "/" if f else "")
    if f:
        try:
            s = f.read_text(encoding="utf-8")
            if s.count(BEGIN) != 1 or s.count(END) != 1 or s.index(BEGIN) > s.index(END):
                raise ValueError(f"needs exactly one {BEGIN} then one {END}")
            f.write_text(s[:s.index(BEGIN) + len(BEGIN)] + "\n" + body + "\n" + s[s.index(END):], encoding="utf-8")
        except (OSError, ValueError) as e:
            print(f"roadmap_rank: cannot update {f}: {e}", file=sys.stderr)
            return 2
        print(f"roadmap_rank: updated {f}", file=sys.stderr)
    else:
        print(body)
    if a.strict and (r["missing"] or r["unresolved"]):
        print(f"roadmap_rank: --strict: idea-critic missing for {r['missing'] or 'none'}, unresolved REVISE {r['unresolved'] or 'none'}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
