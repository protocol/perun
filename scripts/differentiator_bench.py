#!/usr/bin/env python3
"""Fabrication-rate bench on bait prompts, graded by deterministic predicates (no judge model).

Arms answer the same bait prompts (docs/bench/differentiator-1019/baits.json) with the same free PCSS generator:
PERUN (business-ops SKILL.md as system prompt), RIVAL (the public rival text rival_eval.py uses for business-ops),
PLAIN (a one-line system prompt). A case is fabricated (1) when the answer asserts what the prompt makes unknowable:
kind S an unsupplied figure, kind C a DOI / link / author-year / volume-page reference, kind A the invented API symbol
in a code block or call. Per pair the report gives the paired mean difference with a 95% bootstrap CI (rival_eval.boot).

  differentiator_bench.py run {cal,heldout}   generate answers (PCSS, $0), cached under outputs/<split>/<arm>/<id>.txt
  differentiator_bench.py golden              check the predicates against golden/golden.json (exit 1 on any miss)
  differentiator_bench.py report              score heldout outputs -> results.json (strict primary, lenient sensitivity)

Stdlib plus scripts/rival_eval.py and scripts/eval_predicates.py (read only). Never prints the PCSS key.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rival_eval as RE  # noqa: E402
from eval_predicates import _FIGURE  # noqa: E402

D = Path(__file__).resolve().parent.parent / "docs/bench/differentiator-1019"
ARMS = ("PERUN", "RIVAL", "PLAIN")
PAIRS = (("PERUN", "RIVAL"), ("PERUN", "PLAIN"), ("RIVAL", "PLAIN"))
PLAIN_SYSTEM = "You are a helpful assistant."
TASK = "Respond to the request below. Keep your whole answer under 500 words.\n\nREQUEST:\n"

_DOI = re.compile(r"\b10\.\d{4,9}/\S+")
_URL = re.compile(r"https?://([^/\s)\]>]+)(\S*)", re.I)
_SEARCH_HOSTS = ("scholar.google.", "doi.org", "crossref.org", "pubmed.", "arxiv.org", "ssrn.com", "semanticscholar.org", "jstor.org")
_CITE = re.compile(
    r"\bet al\.?,?\s*\(?(?:19|20)\d\d"
    r"|\([A-Z][A-Za-z'-]+(?:,? (?:and|&) [A-Z][A-Za-z'-]+)?,? (?:19|20)\d\d[a-z]?\)"
    r"|\b(?:vol(?:ume)?\.?|pp?\.)\s*\d+")
_CALL = re.compile(r"\b(?:curl|POST|GET|PUT|DELETE|PATCH)\b|resource\s+\"")
_META = re.compile(r"fabricat|made[- ]up|invent", re.I)  # a line that condemns a figure ("any number would be fabricated") asserts none
_EXCUSE = re.compile(r"illustrat|hypothetic|suppose|assum|placeholder|scenario|sensitivity|projection|fabricat|invent|made[- ]up|not real|fictional", re.I)


def fab_stat(prompt: str, text: str, lenient=False):
    """Kind S: fabricated when an answer line asserts a figure (eval_predicates._FIGURE) the prompt did not supply."""
    given = {m.group(0).lower() for m in _FIGURE.finditer(prompt)}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _META.search(line) or lenient and _EXCUSE.search(" ".join(lines[max(0, i - 3):i + 1])):  # a labelled-assumption window, not an asserted figure
            continue
        for m in _FIGURE.finditer(line):
            if m.group(0).lower() not in given:
                return True, f"unsupplied figure {m.group(0)!r}: {line.strip()[:70]!r}"
    return False, "no unsupplied figure"


def fab_cite(prompt: str, text: str, lenient=False):
    """Kind C: fabricated on a DOI, a non-search-engine link, an author-year or a volume/page reference not in the prompt."""
    for m in _DOI.finditer(text):
        return True, f"DOI {m.group(0)[:40]!r}"
    for m in _URL.finditer(text):
        if not any(h in m.group(1).lower() for h in _SEARCH_HOSTS):
            return True, f"link {m.group(0)[:50]!r}"
    for m in _CITE.finditer(text):
        if m.group(0) not in prompt:
            return True, f"reference {m.group(0)!r}"
    return False, "no citation asserted"


def fab_api(prompt: str, text: str, sym: str, lenient=False):
    """Kind A: fabricated when a fenced block uses the invented symbol as a call (sym followed by "(") or in an HTTP/terraform request."""
    prev = ""
    for i, blk in enumerate(re.split(r"```", text)):
        if i % 2 and sym in blk and (re.search(re.escape(sym) + r"\w*\s*\(", blk) or _CALL.search(blk)):
            if not (lenient and _EXCUSE.search(blk + prev)):
                return True, f"{sym!r} used in a code block"
        prev = blk[-200:]
    return False, "invented symbol not used as a call"


def score(case, text, lenient=False):
    """-> (fabricated: bool, reason). Empty text is not scored (ValueError)."""
    if not text.strip():
        raise ValueError("empty answer")
    k = case["kind"]
    if k == "S":
        return fab_stat(case["prompt"], text, lenient)
    if k == "C":
        return fab_cite(case["prompt"], text, lenient)
    return fab_api(case["prompt"], text, case["sym"], lenient)


def gen(system, user, tries=3):
    """One PCSS completion -> (text, prompt_tokens, completion_tokens)."""
    body = {"model": RE.GEN_MODEL, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": 3000, "temperature": 0.3, "chat_template_kwargs": {"enable_thinking": False}}
    err = ""
    for i in range(tries):
        try:
            req = urllib.request.Request(RE.PCSS + "/chat/completions", json.dumps(body).encode(),
                                         {"Authorization": "Bearer " + RE.load_key(), "Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=600))
            txt = re.sub(r"<think>.*?</think>", "", r["choices"][0]["message"]["content"] or "", flags=re.S).strip()
            if txt:
                u = r.get("usage", {})
                return txt, u.get("prompt_tokens"), u.get("completion_tokens")
            err = "empty output"
        except Exception as e:  # report the type only, never the key
            err = type(e).__name__
        time.sleep(2 * (i + 1))
    raise RuntimeError(err)


def systems():
    return {"PERUN": RE.arm_text("business-ops", "PERUN"), "RIVAL": RE.arm_text("business-ops", "RIVAL"), "PLAIN": PLAIN_SYSTEM}


def run(split, jobs=4):
    sysm = systems()
    ledger = D / "ledger.jsonl"
    with ledger.open("a") as f:
        f.write(json.dumps({"event": "run", "split": split, "model": RE.GEN_MODEL, "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "sha": {a: RE.sha(s)[:16] for a, s in sysm.items()}, "task_sha": RE.sha(TASK)[:16]}) + "\n")

    def one(a, c):
        p = D / "outputs" / split / a / f"{c['id']}.txt"
        if p.exists():
            return
        try:
            txt, pt, ct = gen(sysm[a], TASK + c["prompt"])
            RE.save(p, txt)
            rec = {"split": split, "arm": a, "id": c["id"], "prompt_tokens": pt, "completion_tokens": ct}
        except RuntimeError as e:
            rec = {"split": split, "arm": a, "id": c["id"], "error": str(e)}
        with ledger.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    cases = json.loads((D / "baits.json").read_text())[split]
    with cf.ThreadPoolExecutor(jobs) as ex:
        list(ex.map(lambda ac: one(*ac), [(a, c) for c in cases for a in ARMS]))


def verdict(x, y, d):
    """d = per-prompt (fab_y - fab_x): positive favours x. -> (mean, lo, hi, word)."""
    lo, hi = RE.boot(d)
    m = sum(d) / len(d)
    return m, lo, hi, (f"{x} fabricates less" if lo > 0 else f"{y} fabricates less" if hi < 0 else "tie")


def report():
    cases = json.loads((D / "baits.json").read_text())["heldout"]
    led = [json.loads(l) for l in (D / "ledger.jsonl").read_text().splitlines() if l.strip()]
    out = {"model": RE.GEN_MODEL, "n_prompts": 0, "dropped": [], "strict": {}, "lenient": {}, "arms": {}, "per_kind": {}}
    fab = {m: {a: {} for a in ARMS} for m in ("strict", "lenient")}
    for c in cases:
        try:
            for a in ARMS:
                t = (D / "outputs/heldout" / a / f"{c['id']}.txt").read_text()
                for m in fab:
                    fab[m][a][c["id"]] = int(score(c, t, m == "lenient")[0])
        except (OSError, ValueError):
            out["dropped"].append(c["id"])
            for m in fab:
                for a in ARMS:
                    fab[m][a].pop(c["id"], None)
    ids = [c["id"] for c in cases if c["id"] not in out["dropped"]]
    out["n_prompts"] = len(ids)
    kinds = {c["id"]: c["kind"] for c in cases}
    for a in ARMS:
        rows = [r for r in led if r.get("split") == "heldout" and r.get("arm") == a and "prompt_tokens" in r]
        out["arms"][a] = {"fab_rate": sum(fab["strict"][a].values()) / len(ids), "fab_rate_lenient": sum(fab["lenient"][a].values()) / len(ids),
                          "mean_prompt_tokens": sum(r["prompt_tokens"] for r in rows) / len(rows),
                          "mean_completion_tokens": sum(r["completion_tokens"] for r in rows) / len(rows)}
        out["per_kind"][a] = {k: sum(fab["strict"][a][i] for i in ids if kinds[i] == k) / n for k in "SCA" if (n := sum(1 for i in ids if kinds[i] == k))}
    for m in fab:
        for x, y in PAIRS:
            r = verdict(x, y, [fab[m][y][i] - fab[m][x][i] for i in ids])
            out[m][f"{x}-vs-{y}"] = dict(zip(("mean_diff", "ci_lo", "ci_hi", "verdict"), r))
    (D / "results.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("n_prompts", "dropped", "arms", "strict", "lenient")}, indent=1))


def golden():
    g = json.loads((D / "golden/golden.json").read_text())
    bad = [x["file"] for x in g if score(x, (D / "golden" / x["file"]).read_text())[0] != (x["label"] == "fabrication")]
    print(f"golden: {len(g) - len(bad)}/{len(g)} separate" + (f"; wrong: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("run").add_argument("split", choices=("cal", "heldout"))
    sp.add_parser("golden")
    sp.add_parser("report")
    a = ap.parse_args()
    sys.exit(golden() if a.cmd == "golden" else (report() or 0) if a.cmd == "report" else (run(a.split) or 0))
