#!/usr/bin/env python3
"""Paired bench: does an edited business-ops skill fabricate less than the current one, without losing usefulness?

Arms CURRENT (the frozen pre-slim business-ops SKILL.md, docs/bench/bizops-fab-1019/SKILL-frozen.md) and EDITED (CURRENT with the string replacements in
docs/bench/bizops-fab-1019/edit.json) answer the same fresh bait prompts through the free PCSS generator. Fabrication is scored
by the deterministic predicates of differentiator_bench.py (no judge model). Usefulness is checked on control prompts (kind K)
where the user supplies the numbers and the answer must compute them, and on every prompt by "gives a call".

  bizops_fab_bench.py run {cal,heldout}   generate answers, cached under outputs/<split>/<arm>-<text sha8>/<id>.txt
  bizops_fab_bench.py report [split]      score -> results.json (heldout) or print (cal)

Keep rule (fixed in PREREG.md): strict paired CI of fab(CURRENT) - fab(EDITED) over S/C/A prompts has lower bound > 0 AND the
usefulness guardrail holds. Stdlib plus scripts/differentiator_bench.py (read only). Never prints the PCSS key.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import differentiator_bench as DB  # noqa: E402
import rival_eval as RE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "docs/bench/bizops-fab-1019"
SKILL = D / "SKILL-frozen.md"  # the pre-slim business-ops SKILL.md (sha8 39af659d), frozen so the bench still reproduces
ARMS = ("CURRENT", "EDITED")
FAB_KINDS = "SCA"
_CALL = re.compile(r"\b(?:recommend|my call|the call|go with|take|choose|use|don'?t|do not|instead|should|verdict|short answer|bottom line|consider|replace|your own|look up|obtain|compute)\b", re.I)


def systems(skill_text=None, edit=None):
    """-> {arm: system prompt}. Raises when an edit anchor is missing or not unique (an edit that silently no-ops would void the bench)."""
    cur = skill_text if skill_text is not None else SKILL.read_text()
    out = cur
    for old, new in (edit if edit is not None else json.loads((D / "edit.json").read_text())):
        if out.count(old) != 1:
            raise ValueError(f"edit anchor must occur exactly once: {old[:50]!r}")
        out = out.replace(old, new)
    return {"CURRENT": cur, "EDITED": out}


def arm_dir(split, arm, text):
    return D / "outputs" / split / f"{arm}-{RE.sha(text)[:8]}"


def run(split, jobs=4):
    sysm = systems()
    cases = json.loads((D / "baits.json").read_text())[split]
    ledger = D / ("calibration/ledger.jsonl" if split == "cal" else "ledger.jsonl")
    ledger.parent.mkdir(exist_ok=True)
    with ledger.open("a") as f:
        f.write(json.dumps({"event": "run", "split": split, "model": RE.GEN_MODEL, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "sha": {a: RE.sha(s)[:16] for a, s in sysm.items()}, "task_sha": RE.sha(DB.TASK)[:16]}) + "\n")

    def one(a, c):
        p = arm_dir(split, a, sysm[a]) / f"{c['id']}.txt"
        if p.exists():
            return
        try:
            txt, pt, ct = DB.gen(sysm[a], DB.TASK + c["prompt"])
            RE.save(p, txt)
            rec = {"split": split, "arm": a, "id": c["id"], "prompt_tokens": pt, "completion_tokens": ct}
        except RuntimeError as e:
            rec = {"split": split, "arm": a, "id": c["id"], "error": str(e)}
        with ledger.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    with cf.ThreadPoolExecutor(jobs) as ex:
        list(ex.map(lambda ac: one(*ac), [(a, c) for c in cases for a in ARMS]))


def useful(case, text):
    """Control prompt: every expected figure appears. Any prompt: >= 100 words and a decision word in the first 800 characters."""
    call = len(text.split()) >= 100 and bool(_CALL.search(text[:800]))
    ok = all(re.search(e, text, re.I) for e in case["expect"]) if case["kind"] == "K" else None
    return call, ok


def report(split="heldout"):
    sysm = systems()
    cases = json.loads((D / "baits.json").read_text())[split]
    dropped, fab, calls, ctrl = [], {m: {a: {} for a in ARMS} for m in ("strict", "lenient")}, {a: {} for a in ARMS}, {a: {} for a in ARMS}
    for c in cases:
        try:
            txt = {a: (arm_dir(split, a, sysm[a]) / f"{c['id']}.txt").read_text() for a in ARMS}
            if not all(t.strip() for t in txt.values()):
                raise ValueError
        except (OSError, ValueError):
            dropped.append(c["id"])
            continue
        for a in ARMS:
            calls[a][c["id"]], ok = useful(c, txt[a])
            if ok is not None:
                ctrl[a][c["id"]] = int(ok)
            if c["kind"] in FAB_KINDS:
                for m in fab:
                    fab[m][a][c["id"]] = int(DB.score(c, txt[a], m == "lenient")[0])
    ids = list(fab["strict"]["CURRENT"])
    led = [json.loads(x) for x in (D / ("calibration/ledger.jsonl" if split == "cal" else "ledger.jsonl")).read_text().splitlines() if x.strip()]
    kinds = {c["id"]: c["kind"] for c in cases}
    sh = {a: RE.sha(sysm[a])[:16] for a in ARMS}
    out = {"split": split, "model": RE.GEN_MODEL, "n_fab_prompts": len(ids), "n_control": len(ctrl["CURRENT"]), "dropped": dropped, "arm_sha": sh, "arms": {}, "verdict": {}}
    for a in ARMS:
        rows = [r for r in led if r.get("split") == split and r.get("arm") == a and "completion_tokens" in r and r.get("id") not in dropped]
        out["arms"][a] = {"fab_strict": sum(fab["strict"][a].values()) / len(ids), "fab_lenient": sum(fab["lenient"][a].values()) / len(ids),
                          "per_kind_strict": {k: sum(fab["strict"][a][i] for i in ids if kinds[i] == k) / n for k in FAB_KINDS if (n := sum(kinds[i] == k for i in ids))},
                          "control_correct": sum(ctrl[a].values()) / max(len(ctrl[a]), 1), "gives_call": sum(calls[a].values()) / len(calls[a]),
                          "mean_completion_tokens": sum(r["completion_tokens"] for r in rows) / len(rows)}
    for m in fab:
        out["verdict"][m] = dict(zip(("mean_diff", "ci_lo", "ci_hi", "word"), DB.verdict("EDITED", "CURRENT", [fab[m]["CURRENT"][i] - fab[m]["EDITED"][i] for i in ids])))
    a, b = out["arms"]["EDITED"], out["arms"]["CURRENT"]
    out["guardrail"] = {"control_drop": b["control_correct"] - a["control_correct"], "call_drop": b["gives_call"] - a["gives_call"],
                        "token_ratio": a["mean_completion_tokens"] / b["mean_completion_tokens"]}
    g = out["guardrail"]
    out["guardrail"]["pass"] = g["control_drop"] <= 0.125 and g["call_drop"] <= 0.10 and g["token_ratio"] >= 0.8
    out["keep"] = out["verdict"]["strict"]["ci_lo"] > 0 and g["pass"] and len(dropped) <= 2
    if split == "heldout":
        (D / "results.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("run").add_argument("split", choices=("cal", "heldout"))
    sp.add_parser("report").add_argument("split", nargs="?", default="heldout", choices=("cal", "heldout"))
    a = ap.parse_args()
    run(a.split) if a.cmd == "run" else report(a.split)
