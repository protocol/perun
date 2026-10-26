#!/usr/bin/env python3
"""Deterministic answer keys and scorer for the business-ops bench (no LLM judge, no network, stdlib only).

  keys_score.py keys               derive keys.json from the landed bizops-r4-1018 held scenarios (read-only)
  keys_score.py score KEYS OUTDIR  grade saved outputs (OUTDIR/<scenario-id>.txt) against KEYS, print JSON

Per-scenario key (rule-derived from the prompt text only, so it is reproducible and carries no judgement):
  lead_number  true when the prompt contains a digit: the first 500 characters of the output must contain a digit
               (lead with a call or number, not a preamble).
  numbers      figures computable from the prompt by a fixed rule; the output must contain one of them
               (any listed string, as a whole number token). Rules, each applied only when its inputs are found:
               runway = bank / burn (1 decimal), lifetime = 100 / monthly churn percent (1 decimal, or
               "N months" from 10), ltv_cac = LTV / CAC (1 and 2 decimals), unit_margin = price - cost (as a
               dollar figure) where the prompt states "$P ... production cost|cost of goods sold|COGS of $C". Anything else is left unchecked.
  route        true when the prompt asks about a jurisdiction-specific matter (law, tax, regulator, permit, export,
               securities, IP ...): the output must name a professional (attorney, CPA, counsel, regulator ...).
  no_bench     true unless the prompt itself cites a benchmark: the output must not attribute a figure to an
               industry average, a study, a report or a survey (no fabricated benchmarks). Plain rules of thumb
               (e.g. "3:1 LTV:CAC") are not flagged.
A scenario passes when every active check holds. Empty or missing output = fail. Aggregate = pass rate.
"""
import json, re, sys
from pathlib import Path

D = Path(__file__).resolve().parent
SRC = D.parent / "bizops-r4-1018"
NUM = r"\$\s?([\d,]+(?:\.\d+)?)"
JUR = re.compile(r"\b(?:law|laws|legal|legally|tax|taxes|taxation|regulat\w+|FDA|HIPAA|GDPR|SEC|IRS|VAT|nexus|jurisdictions?|licen[sc]\w+|permits?|compliance|export|antitrust|securities|trademarks?|patents?|malpractice|quarantine|procurement|predatory|statutes?|attorney|lawyer|counsel)\b", re.I)
PRO = re.compile(r"attorney|lawyer|counsel|solicitor|\bCPA\b|accountant|tax (?:advisor|adviser|professional|preparer)|licensed|regulator|compliance (?:officer|specialist)|specialist|professional", re.I)
BENCH_IN_PROMPT = re.compile(r"benchmark|industry average|industry standard", re.I)
BENCH_OUT = re.compile(r"industry (?:average|benchmark|standard)s?\b|according to (?:a |an |the |recent )?(?:\w+ ){0,2}(?:report|study|survey|research)|(?:studies|research|surveys|reports) (?:show|shows|found|indicate|suggest)|benchmarks? (?:show|shows|of|is|are) ", re.I)


def _f(s):
    return float(s.replace(",", ""))


def _n(v, ds, months=False):
    """Strings a correct answer may print: v at each decimal count in ds, plus "N months" for whole-month figures of 10 or more."""
    out = {f"{v:.{d}f}" for d in ds}
    if months and v >= 10:
        out.add(f"{round(v)} months")
    return out


def _m(v):
    """Dollar strings for a margin: $66.00 and $66, $1.60 and $1.6 (sign dropped, a loss is the same figure)."""
    s = f"${abs(v):,.2f}"
    return {s, s.rstrip("0").rstrip(".")}


def numbers(prompt):
    """Computable figures from the prompt by fixed rules; [] when no rule applies."""
    out = set()
    bank = re.search(NUM + r" in (?:the |our )?bank", prompt)
    burn = re.search(r"burn(?: rate)? of (?:about |roughly |approximately )?" + NUM, prompt)
    if bank and burn and _f(burn.group(1)):
        out |= _n(_f(bank.group(1)) / _f(burn.group(1)), (1,), True)
    churn = re.search(r"monthly churn(?: rate)?(?: \w+){0,3}? (?:of|at|is|sits at|runs at) (?:about |roughly )?(\d+(?:\.\d+)?)\s?%", prompt)
    if churn and _f(churn.group(1)):
        out |= _n(100 / _f(churn.group(1)), (1,), True)
    ltv = re.search(r"(?:lifetime value|LTV)[^$.]{0,40}" + NUM, prompt)
    cac = re.search(r"(?:acquisition cost|CAC)[^$.]{0,40}" + NUM, prompt)
    if ltv and cac and _f(cac.group(1)):
        out |= _n(_f(ltv.group(1)) / _f(cac.group(1)), (1, 2))
    um = re.search(NUM + r"[^$.]{0,60}?(?:production cost|cost of goods sold|COGS)[^$.]{0,30}?" + NUM, prompt)
    if um:
        out |= _m(_f(um.group(1)) - _f(um.group(2)))
    return sorted(out)


def derive(prompt):
    """Key for one prompt: lead_number, numbers, route, no_bench."""
    return {"lead_number": bool(re.search(r"\d", prompt)), "numbers": numbers(prompt),
            "route": bool(JUR.search(prompt)), "no_bench": not BENCH_IN_PROMPT.search(prompt)}


def grade(key, text):
    """Grade one output text against one key: {"pass": bool, "why": [failure codes]}."""
    if not text.strip():
        return {"pass": False, "why": ["empty"]}
    why = []
    if key["lead_number"] and not re.search(r"\d", text[:500]):
        why.append("no-lead-number")
    if key["numbers"] and not any(re.search(r"(?<![\d.,])" + re.escape(n) + r"(?!\d|\.\d)", text) for n in key["numbers"]):
        why.append("wrong-arithmetic")
    if key["route"] and not PRO.search(text):
        why.append("no-professional-route")
    if key["no_bench"] and BENCH_OUT.search(text):
        why.append("fabricated-benchmark")
    return {"pass": not why, "why": why}


def build():
    """Keys for every held scenario of the landed bizops-r4-1018 bench."""
    return {s["id"]: derive(s["prompt"]) for s in json.loads((SRC / "scenarios-heldout.json").read_text())}


def score(keys, outdir):
    """Grade OUTDIR/<id>.txt for every key; a missing file fails."""
    res = {}
    for sid, key in keys.items():
        f = Path(outdir) / f"{sid}.txt"
        res[sid] = grade(key, f.read_text() if f.exists() else "")
    return {"n": len(res), "pass_rate": sum(r["pass"] for r in res.values()) / max(len(res), 1), "scenarios": res}


if __name__ == "__main__":
    if sys.argv[1:2] == ["keys"]:
        (D / "keys.json").write_text(json.dumps(build(), indent=1, sort_keys=True) + "\n")
    elif sys.argv[1:2] == ["score"] and len(sys.argv) == 4:
        print(json.dumps(score(json.loads(Path(sys.argv[2]).read_text()), sys.argv[3]), indent=1))
    else:
        sys.exit(__doc__)
