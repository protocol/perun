#!/usr/bin/env python3
"""Writes the confirmation held-out scenarios (scenarios_held.json) with r2's writer brief and r1's validity checks (every listed literal occurs in
the notes, >= 4 figures, gold figures in the notes, gold action is not the drafting task). Only 25 of the 175 (kind, domain) pairs are unused by r1
and r2, so the pair-level disjointness r1 and r2 used cannot reach the preregistered n: the 25 unused pairs come first, then every pair again with a
new variant seed, and a scenario is kept only when at most 20% of its 10-word shingles occur in any r1 or r2 scenario or in a scenario already kept.
The first MAX valid scenarios in that fixed order are kept; fewer than MIN means the bench stops with no verdict. usage: gen.py"""
import concurrent.futures as cf, json, random, sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fabjudge as f  # noqa: E402  (sets bench.D to this directory, patches the extractor)
import fixed2  # noqa: E402
sys.path.insert(0, str(f.D.parents[2] / "scripts"))
import bench_check as bc  # noqa: E402
b, D, R1 = f.b, f.D, f.R1
R2 = D.parent / "comms-outcome-r2-1019"
MAX, MIN, ROUNDS, OVERLAP = 500, 243, 6, 0.2


def make(k, d, sid, brief):
    for att in range(4):
        try:
            j = b.parse_json(b.call("write", b.WRITER, "You write synthetic test scenarios.", brief.format(kind_desc=b.KINDS[k], domain=d, seed=f"{sid}-{att}"), 0.9, id=sid, att=att))
        except RuntimeError:
            continue
        if not j or not all(isinstance(j.get(x), str) and j[x].strip() for x in ("prompt", "recipient", "number_literal", "owner_literal", "deadline_literal", *b.QS)) or not isinstance(j.get("facts"), list):
            continue
        facts = [x for x in dict.fromkeys([j["number_literal"], j["owner_literal"], j["deadline_literal"], *map(str, j["facts"])]) if x.strip()]
        sc = {"id": sid, "split": "held", "kind": k, "domain": d, "prompt": j["prompt"], "recipient": j["recipient"], **{x: j[x] for x in b.QS}, "facts": facts}
        if not (b.dropped(sc["prompt"], facts) or len(facts) < 4 or len(b._numbers(sc["prompt"])) < 4 or fixed2.bad(sc)):
            return sc
    return None


def overlap(sc, pool):
    s = bc.shingles(" ".join(str(v) for k, v in sc.items() if k != "id"))
    return len(s & pool) / len(s) if s else 0


if __name__ == "__main__":
    prior = [s for p, sp in ((R1, "tune"), (R1, "held"), (R2, "held")) for s in json.loads((p / f"scenarios_{sp}.json").read_text())]
    pool = set().union(*[bc.shingles(" ".join(str(v) for k, v in s.items() if k != "id")) for s in prior])
    taken = {(s["kind"], s["domain"]) for s in prior}
    pairs = [(k, d) for d in b.DOMAINS for k in b.KINDS]
    rng = random.Random(4020)
    fresh = [p for p in pairs if p not in taken]
    order = [fresh[i] for i in rng.sample(range(len(fresh)), len(fresh))]
    brief = (D / "prompts/writer_brief.txt").read_text()
    ok, rejected = [], 0
    for rd in range(ROUNDS):
        batch = order if rd == 0 else rng.sample(pairs, len(pairs))
        if rd == 0:
            batch += rng.sample([p for p in pairs if p in taken], len(taken))
        with cf.ThreadPoolExecutor(b.JOBS) as ex:
            res = list(ex.map(lambda i: make(*batch[i], f"conf{rd}x{i:03d}", brief), range(len(batch))))
        for r in filter(None, res):
            if len(ok) < MAX and overlap(r, pool) <= OVERLAP:
                ok.append(r)
                pool |= bc.shingles(" ".join(str(v) for k, v in r.items() if k != "id"))
            else:
                rejected += 1
        if len(ok) >= MAX:
            break
    for n, r in enumerate(ok, 1):
        r["id"] = f"conf{n:03d}"
    print(f"{len(ok)} scenarios kept, {rejected} over the overlap bound or beyond MAX; need >= {MIN}", {k: sum(r["kind"] == k for r in ok) for k in b.KINDS})
    if len(ok) < MIN:
        sys.exit("fewer than MIN valid scenarios: no verdict")
    (D / "scenarios_held.json").write_text(json.dumps(ok, indent=1) + "\n")
