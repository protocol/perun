#!/usr/bin/env python3
"""Failure evidence for the comms-quality work: defects counted by comms_lint, not asserted. (See README.txt.)
usage: evidence.py prs PRS.json | docs | bench | all PRS.json    (writes/prints JSON; `all` writes evidence.json)
prs: PRS.json = [{"number", "title", "body"}] (the last N pull request bodies from the REST API); every body is linted as `pr`.
docs: docs/*.md and README.md: first-paragraph length, longest paragraph, paragraphs over 150 words, and the BLUF rule.
bench: the 20 committed model outputs of docs/bench/comms-rubricfree-1016, linted with its scenario text as --source.
Counts only; no body text is stored (a PR body may name people). Stdlib only."""
import collections
import json
import re
import sys
from pathlib import Path

D = Path(__file__).resolve().parent
ROOT = D.parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/communication-structure/scripts"))
import comms_lint  # noqa: E402

KIND = {"01": "pr", "02": "status", "03": "incident", "04": "message", "05": "message", "06": "message", "07": "release", "08": "decision", "09": "message", "10": "decision"}


def failing(res):
    return [r["rule"] for r in res["rules"] if not r["ok"] and not r["advisory"]]


def prs(path):
    rows, tally = [], collections.Counter()
    for p in json.loads(Path(path).read_text()):
        body = (p.get("body") or "").strip()
        if not body:
            rows.append({"number": p["number"], "empty": True})
            tally["empty body"] += 1
            continue
        res = comms_lint.lint("pr", body)
        lead = [r for r in res["rules"] if r["rule"] == "lead"][0]["hits"]
        fails = failing(res)
        tally.update(fails)
        tally.update("warn:" + r["rule"] for r in res["rules"] if r["advisory"] and not r["ok"])
        rows.append({"number": p["number"], "words": res["words"], "lines": res["lines"], "fails": fails, "warns": [r["rule"] for r in res["rules"] if r["advisory"] and not r["ok"]],
                     "lead_words": next((int(m.group(1)) for h in lead for m in [re.search(r"lead is (\d+) words", h["problem"])] if m), None)})
    n = len(rows)
    return {"n": n, "empty": tally["empty body"], "pass_bar": sum(1 for r in rows if not r.get("empty") and not r["fails"]),
            "words_median": sorted(r["words"] for r in rows if "words" in r)[len([r for r in rows if "words" in r]) // 2] if any("words" in r for r in rows) else None,
            "defects": dict(tally), "rows": rows}


def paragraphs(text):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip() and not p.lstrip().startswith(("#", "|", "---", "["))]


def docs():
    rows = []
    for f in sorted(list((ROOT / "docs").glob("*.md")) + [ROOT / "README.md"]):
        text = f.read_text(encoding="utf-8")
        paras = paragraphs(text)
        w = [len(p.split()) for p in paras]
        rows.append({"file": str(f.relative_to(ROOT)), "words": len(text.split()), "first_paragraph_words": w[0] if w else 0,
                     "longest_paragraph_words": max(w, default=0), "paragraphs_over_150_words": sum(1 for x in w if x > 150)})
    return {"n": len(rows), "files_with_a_paragraph_over_150_words": sum(1 for r in rows if r["paragraphs_over_150_words"]),
            "first_paragraph_over_60_words": sum(1 for r in rows if r["first_paragraph_words"] > 60), "rows": rows}


def bench():
    B = ROOT / "docs/bench/comms-rubricfree-1016"
    sc = {s["id"]: s["prompt"] for s in json.loads((B / "scenarios.json").read_text())}
    tally, n = collections.Counter(), collections.Counter()
    for arm in ("PERUN", "RIVAL"):
        for i, k in KIND.items():
            txt = re.split(r"\n+(?:-{3,}\s*\n+)?(?:\*\*)?Notes?\s*:", (B / "outputs" / arm / f"{i}.txt").read_text(), maxsplit=1, flags=re.I)[0]
            res = comms_lint.lint(k, txt, sc[i])
            n[arm] += 1
            tally[arm, "pass_bar"] += not failing(res)
            for r in failing(res):
                tally[arm, r] += 1
    return {"outputs_per_arm": 10, "by_arm": {arm: {k[1]: v for k, v in tally.items() if k[0] == arm} for arm in n}}


if __name__ == "__main__":
    cmd = sys.argv[1]
    out = {"prs": lambda: prs(sys.argv[2]), "docs": docs, "bench": bench}
    if cmd == "all":
        res = {"prs": prs(sys.argv[2]), "docs": docs(), "bench": bench()}
        (D / "evidence.json").write_text(json.dumps(res, indent=1) + "\n")
    else:
        res = out[cmd]()
    print(json.dumps({k: v for k, v in res.items() if k != "rows"} if cmd != "all" else {k: {a: b for a, b in v.items() if a != "rows"} for k, v in res.items()}, indent=1))
