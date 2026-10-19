#!/usr/bin/env python3
"""Scenario audit (amendment A1, see AMENDMENT.md): a gold answer must not hold a numeric token or weekday absent from the notes.
usage: audit.py SPLIT [--drop]   -> prints failing ids; --drop rewrites scenarios_SPLIT.json without them.
       audit.py SPLIT --fill N   -> after --drop, writes new valid scenarios (same checks as bench.scen plus this audit) until N remain."""
import random
import json, sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench as b


def bad(sc):
    """Gold fields (decision, action, owner, deadline, number) whose figures or weekdays the notes do not contain."""
    return [q for q in b.QS if b.invented(sc[q], sc["prompt"])]


def fill(split, n):
    S = b.load(split)
    taken = {(s["kind"], s["domain"]) for sp in ("tune", "held") if (b.D / f"scenarios_{sp}.json").exists() for s in b.load(sp)}
    taken |= {(s["kind"], s["domain"]) for s in S}
    rng = random.Random(3019)
    combos = [(k, d) for d in b.DOMAINS for k in b.KINDS if (k, d) not in taken]
    rng.shuffle(combos)
    brief = (b.D / "prompts/writer_brief.txt").read_text()
    nxt = max(int(s["id"][len(split):]) for s in S) + 1
    for k, d in combos:
        if len(S) >= n:
            break
        for att in range(4):
            sid = f"{split}{nxt:02d}"
            try:
                j = b.parse_json(b.call("write", b.WRITER, "You write synthetic test scenarios.", brief.format(kind_desc=b.KINDS[k], domain=d, seed=f"{sid}-{att}"), 0.9, id=sid, att=att, fill=True))
            except RuntimeError:
                continue
            if not j or not all(isinstance(j.get(x), str) and j[x].strip() for x in ("prompt", "recipient", "number_literal", "owner_literal", "deadline_literal", *b.QS)) or not isinstance(j.get("facts"), list):
                continue
            facts = [f for f in dict.fromkeys([j["number_literal"], j["owner_literal"], j["deadline_literal"], *map(str, j["facts"])]) if f.strip()]
            sc = {"id": sid, "split": split, "kind": k, "domain": d, "prompt": j["prompt"], "recipient": j["recipient"], **{x: j[x] for x in b.QS}, "facts": facts}
            if b.dropped(sc["prompt"], facts) or len(facts) < 4 or len(b._numbers(sc["prompt"])) < 4 or bad(sc):
                continue
            S.append(sc); nxt += 1
            break
    (b.D / f"scenarios_{split}.json").write_text(json.dumps(S, indent=1) + "\n")
    print(len(S), "scenarios")


if __name__ == "__main__":
    if "--fill" in sys.argv:
        sys.exit(fill(sys.argv[1], int(sys.argv[sys.argv.index("--fill") + 1])))
    split, S = sys.argv[1], b.load(sys.argv[1])
    fails = {s["id"]: bad(s) for s in S if bad(s)}
    print(f"{len(fails)}/{len(S)} fail", fails)
    if "--drop" in sys.argv:
        (b.D / f"scenarios_{split}.json").write_text(json.dumps([s for s in S if s["id"] not in fails], indent=1) + "\n")
