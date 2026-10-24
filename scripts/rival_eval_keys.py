#!/usr/bin/env python3
"""Deterministic answer-key scoring for rival_eval.py, without editing it (its sha256 is frozen by test_evil_twin_bench_r2.py).

usage: rival_eval_keys.py run|write|changed|check ...   (same arguments as rival_eval.py, plus cost capture)
       rival_eval_keys.py keys SKILL RUNDIR              (answer-key hit rate per arm from cached outputs; offline)

A skill with `<skill>/keys.json` under scripts/eval-fixtures/rival gets, per scenario, 3-6 must-hit and 1-3 must-not regex
items (`must`, `mustnot`, `mustnot_draft`, optional `needs_draft`). `key_score` gives each arm's mean hit rate and the share of
scenarios with any must-not hit, no judge. `install()` (also installs rival_eval_cost) adds key hygiene to `check_split`, adds
an `answer_key` block to each run's results.json, and routes the `keys` subcommand. Side effects: results.json is rewritten
after run_skill; `keys` fails with SystemExit on a missing keys.json or arm directory.
"""
import functools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rival_eval as r  # noqa: E402
import rival_eval_cost as cost  # noqa: E402

# Heuristic, not a parser: a must-not match counts as negated only when one of these words sits within NEG_WINDOW words right
# before it in the same clause, so "not only X" can still mis-score; keys are written to tolerate that (see `violated`).
NEG = re.compile(r"\b(never|don'?t|do not|doesn'?t|won'?t|shouldn'?t|avoid|not|no|without|omit|exclude|instead of)\b", re.I)


NEG_WINDOW = 4
SHIPPED = ("business-ops", "growth-analytics", "idea-critic", "contribution")  # skills that ship keys.json: a missing file must fail, not skip
DRAFT_MIN_WORDS = 15  # a `needs_draft` answer must quote/fence at least this many words of message body


def load_keys(skill):
    """-> {scenario id: {"must": {name: regex}, "mustnot": {...}, "mustnot_draft": {...}}} from <skill>/keys.json, or {} for a skill
    that ships none. Raises SystemExit (fail closed) when a SHIPPED skill's keys.json is missing or empty."""
    f = r.FIX / skill / "keys.json"
    keys = json.loads(f.read_text()) if f.is_file() else {}
    if not keys and skill in SHIPPED:
        raise SystemExit(f"keys: keys.json missing or empty for {skill} (fail closed)")
    return keys


def check_keys(skill):
    """Answer-key hygiene (empty = clean): every held-out id keyed, 3-6 must-hit and 1-3 must-not items, every regex compiles."""
    try:
        keys, bad = load_keys(skill), []
    except SystemExit as e:
        return [str(e)]
    if not keys:
        return bad
    for i, k in keys.items():
        if not isinstance(k, dict) or not isinstance(k.get("must"), dict) or not all(isinstance(k.get(g, {}), dict) for g in ("mustnot", "mustnot_draft")):
            bad.append(f"keys.json {i}: malformed entry (`must` and optional `mustnot`/`mustnot_draft` must be {{name: regex}} objects)")
    if bad:
        return bad
    for sc in r.load_scenarios(skill, "heldout"):
        k = keys.get(sc["id"])
        if not k:
            bad.append(f"keys.json: no key for heldout {sc['id']}")
            continue
        no = len(k.get("mustnot", {})) + len(k.get("mustnot_draft", {}))
        if not 3 <= len(k.get("must", {})) <= 6 or not 1 <= no <= 3:
            bad.append(f"keys.json {sc['id']}: needs 3-6 must and 1-3 mustnot items")
    for i, k in keys.items():
        for grp in ("must", "mustnot", "mustnot_draft"):
            for name, rx in k.get(grp, {}).items():
                try:
                    re.compile(rx)
                except re.error as e:
                    bad.append(f"keys.json {i}/{name}: bad regex ({e})")
    return bad


def draft_text(t):
    """Only the parts of an answer that read as a drafted public message: > quoted lines and fenced blocks."""
    out, fence = [], False
    for ln in t.splitlines():
        if ln.lstrip().startswith("```"):
            fence = not fence
        elif fence or ln.lstrip().startswith(">"):
            out.append(ln)
    return "\n".join(out)


def violated(rxs, text):
    """Names of must-not regexes with at least one match not negated by a NEG word within NEG_WINDOW words right before it in
    the same clause, so "never promise a guaranteed profit" is not a violation but "No, you should definitely form an LLC" is.
    Nothing is blanked: a bracketed or angle-bracketed name still counts, so use a generic placeholder like [Company]."""
    out = []
    for n, rx in rxs.items():
        for s in re.split(r"(?<=[.!?])\s+|\n", text):
            if any(not NEG.search(" ".join(re.split(r"[,;:()]|\s[-\u2013\u2014]+\s", s[:m.start()])[-1].split()[-NEG_WINDOW:]))
                   for m in re.finditer(rx, s, re.I)):
                out.append(n)
                break
    return out


def key_score(skill, outs):
    """Deterministic outcome score: per arm, mean fraction of must-hit items found (hit_rate) and share of scenarios with any
    must-not hit (violation_rate). outs = {arm: {scenario id: answer text}}; every keyed id counts for every arm, and an arm with no answer for one scores 0 hits there (n stays len(keys)).
    Regex only, case-insensitive; must-nots skip negated sentences (see `violated`); `mustnot_draft` is checked against the
    drafted-message lines only; `needs_draft` keys flag `no_draft` (counted as a violation) unless the answer quotes/fences >= DRAFT_MIN_WORDS words.
    ponytail: keyword match proves presence, not quality; upgrade to a PCSS item-presence judge if regex misses paraphrases."""
    keys = load_keys(skill)
    ids = list(keys)
    res = {}
    for a in outs:
        per = {}
        for i in ids:
            t, k = outs[a].get(i, ""), keys[i]
            if i not in outs[a]:  # no output for this arm: a miss, not a dropped scenario
                per[i] = dict(hits=0, of=len(k["must"]), missed=sorted(k["must"]), violated=[], no_draft=False, missing=True)
                continue
            hit = [n for n, rx in k["must"].items() if re.search(rx, t, re.I | re.S)]
            d = draft_text(t)
            bad = violated(k.get("mustnot", {}), t) + violated(k.get("mustnot_draft", {}), d)
            no_draft = bool(k.get("needs_draft")) and len(re.sub(r"^\s*>+", "", d, flags=re.M).split()) < DRAFT_MIN_WORDS
            per[i] = dict(hits=len(hit), of=len(k["must"]), missed=sorted(set(k["must"]) - set(hit)), violated=bad, no_draft=no_draft)
        n = len(per)
        res[a] = dict(n=n, hit_rate=round(sum(p["hits"] / p["of"] for p in per.values()) / n, 3) if n else None,
                      violation_rate=round(sum(bool(p["violated"]) or p["no_draft"] for p in per.values()) / n, 3) if n else None, per_scenario=per)
    return res


def _summary(skill, outs):
    return {a: {k: x for k, x in v.items() if k != "per_scenario"} for a, v in key_score(skill, outs).items()}


def _outs(d, skill, split):
    """{arm: {scenario id: text}} for the CURRENT prompts only: file `<id>-<sha(prompt)[:8]>.txt`, so stale hashes are ignored."""
    return {a: {sc["id"]: f.read_text() for sc in r.load_scenarios(skill, split)
                if (f := Path(d) / "outputs" / a / f"{sc['id']}-{r.sha(sc['prompt'])[:8]}.txt").exists()} for a in r.ARMS}


def keys_cmd(skill, rundir):
    """Rescore cached held-out outputs under RUNDIR/outputs/<ARM>/<id>-<current prompt hash>.txt and print the per-arm summary as JSON."""
    if not load_keys(skill):
        raise SystemExit(f"keys: no keys.json for {skill} (fail closed)")
    for x in r.ARMS:
        if not (Path(rundir) / "outputs" / x).is_dir():
            raise SystemExit(f"keys: missing arm directory {Path(rundir) / 'outputs' / x}")
    print(json.dumps(_summary(skill, _outs(rundir, skill, "heldout")), indent=1))


def install():
    """Wrap rival_eval in place (idempotent), cost capture included. Call before main()."""
    if getattr(r, "_keys_installed", False):
        return
    r._keys_installed = True
    cost.install()
    check_split, run_skill = r.check_split, r.run_skill

    @functools.wraps(check_split)
    def check_split_(skill):
        return check_split(skill) + check_keys(skill)

    @functools.wraps(run_skill)
    def run_skill_(skill, split, backend, out, jobs, cap):
        res = run_skill(skill, split, backend, out, jobs, cap)
        if split == "heldout" and load_keys(skill):  # keys cover the held-out split only
            d = cost.run_dir(out, skill, split)
            res["answer_key"] = _summary(skill, _outs(d, skill, split))
            (d / "results.json").write_text(json.dumps(res, indent=1) + "\n")
        return res

    r.check_split, r.run_skill = check_split_, run_skill_


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    install()
    if argv[:1] == ["keys"]:
        if len(argv) != 3:
            raise SystemExit("usage: rival_eval_keys.py keys SKILL RUNDIR")
        return keys_cmd(argv[1], argv[2])
    return r.main(argv)


if __name__ == "__main__":
    sys.exit(main())
