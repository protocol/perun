#!/usr/bin/env python3
"""Real-fabrication judge for the r2 bench (see PREREGISTERED.md): labels each regex-flagged figure of a message supported or fabricated.

The r1 regex (comms-outcome-1019 fixed.numbers via bench.invented) flags every numeric token or weekday absent from the notes, including a
correctly derived figure; a blind PCSS judge sees the notes, the message and the flagged tokens (never the arm) and decides from the notes.
A message is really fabricated when at least one flagged token is labelled fabricated. Importing this module points bench.D at this directory
(outputs, reads, grades, ledger and judge caches live here); r1's bench.py, fixed.py and fixed2.py stay frozen and are reused unchanged.
usage: fabjudge.py validate [dev|test|all]   |   fabjudge.py run SPLIT ARM..
"""
import concurrent.futures as cf, hashlib, json, re, sys
from pathlib import Path

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
R1 = D.parent / "comms-outcome-1019"
sys.path.insert(0, str(R1))
import bench as b  # noqa: E402
import fixed  # noqa: E402,F401  amendment A2 extractor
import fixed2  # noqa: E402,F401  amendment A3 audit

b.D = D
LEDGER = ["ledger.jsonl"]  # judge validation runs before preregistration, so `validate` logs to validation_ledger.jsonl instead


def _ledger(**e):
    """b.ledger with the target file chosen at run time (LEDGER[0])."""
    import time
    from datetime import datetime, timezone
    now = time.time()
    e = {"ts": int(now), "iso": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **e}
    with b._lock, open(D / LEDGER[0], "a") as f:
        f.write(json.dumps(e) + "\n")


b.ledger = _ledger
JUDGE = "GLM-5.2"  # the r1 grader; blind to the arm, a different model from the generator


def flags(msg, notes):
    return b.invented(msg, notes)


def judge(notes, msg, tokens, model=JUDGE):
    """{token: 'supported'|'fabricated'} for the flagged tokens, cached by content hash under judge/<model>/; {} for no tokens. Missing tokens mean a parse failure (caller counts them)."""
    if not tokens:
        return {}
    user = (D / "prompts/fab_judge.txt").read_text().format(notes=notes, msg=msg, tokens=", ".join(tokens))
    p = D / "judge" / model / (hashlib.sha256(user.encode()).hexdigest()[:20] + ".json")
    txt = b.cached(p, lambda: b.call("judge", model, "You are a strict, fair auditor.", user, 0.0))
    m = re.search(r'"labels"\s*:\s*(\{[^{}]*\})', txt)  # the labels object alone, so a malformed "checks" string cannot void it
    try:
        lab = json.loads(m.group(1)) if m else {}
    except ValueError:
        lab = {}
    return {t: lab[t] for t in tokens if lab.get(t) in ("supported", "fabricated")}


def real_fab(msg, notes, model=JUDGE):
    """(really fabricated?, number of flagged tokens the judge did not label) for one message."""
    t = flags(msg, notes)
    lab = judge(notes, msg, t, model)
    return int("fabricated" in lab.values()), len(t) - len(lab)


def validate(which="all", model=JUDGE):
    """Judge vs hand labels (labels.json) on the r1 sample (sample.json), token level. Returns agreement stats."""
    S = {s["id"]: s for s in json.loads((R1 / "scenarios_held.json").read_text())}
    items = [i for i in json.loads((D / "sample.json").read_text()) if which in ("all", i["split"])]
    lab = json.loads((D / "labels.json").read_text())

    def one(i):
        sc = S[i["id"]]
        msg = (R1 / "outputs/held" / i["arm"] / f"{i['id']}_{i['k']}.txt").read_text()
        t = flags(msg, sc["prompt"])
        return judge(sc["prompt"], msg, t, model).get(i["token"])
    with cf.ThreadPoolExecutor(b.JOBS) as ex:
        got = list(ex.map(one, items))
    gold = ["fabricated" if lab[str(i["n"])]["label"] == "F" else "supported" for i in items]
    n = len(items); agree = sum(g == h for g, h in zip(gold, got))
    tp = sum(g == h == "fabricated" for g, h in zip(gold, got)); fp = sum(h == "fabricated" and g == "supported" for g, h in zip(gold, got))
    fn = sum(g == "fabricated" and h != "fabricated" for g, h in zip(gold, got))
    return dict(split=which, n=n, agree=agree, accuracy=round(agree / n, 3), fabricated_gold=tp + fn, recall=round(tp / max(tp + fn, 1), 3),
                precision=round(tp / max(tp + fp, 1), 3), unlabelled=sum(h is None for h in got), model=model)


if __name__ == "__main__":
    if sys.argv[1] == "validate":
        LEDGER[0] = "validation_ledger.jsonl"
        r = validate(*sys.argv[2:3])
        print(json.dumps(r))
        with open(D / "validation.jsonl", "a") as f:
            f.write(json.dumps(r) + "\n")
