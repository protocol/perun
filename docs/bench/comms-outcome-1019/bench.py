#!/usr/bin/env python3
"""Outcome bench for communication-structure (see PREREGISTERED.md). Free PCSS models only; no claude -p.

usage: bench.py scen SPLIT | run SPLIT ARM.. | report SPLIT ARM..   (BASE=V0 env: the arm others are paired against)   (SPLIT = tune | held)

A message is scored by what a separate reader model can recover from it alone: five fixed questions
(decision, action, owner, deadline, number) answered by each reader, graded against the scenario's gold by a third model.
Guardrails are deterministic: a literal fact dropped, a numeric token or weekday invented (absent from the source notes), and word count.
Every output, read and grade is cached under outputs/, reads/, grades/ and never overwritten; every call is logged to ledger.jsonl.
"""
import concurrent.futures as cf, json, os, random, re, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path

D = Path(__file__).resolve().parent
sys.path.insert(0, str(D.parents[2] / "scripts"))
import rival_eval as R  # noqa: E402

WRITER = "DeepSeek-V4-Flash"
GENERATOR = R.GEN_MODEL          # Qwen3.5-397B-A17B, as in the earlier comms benches
READERS = ("GLM-5.1", "gpt-oss_120b")
GRADER = "GLM-5.2"
SAMPLES = 3                      # generator samples per arm x scenario (temperature 0.7)
QS = ("decision", "action", "owner", "deadline", "number")
JOBS = int(os.environ.get("JOBS", 6))
RIVAL = D.parent / "comms-r5-1017/prompts/RIVAL.txt"   # humanizer v3.1.0, vendored by an earlier bench
KINDS = {
    "decision": "raw notes for a message to a named senior reader (VP, CFO, director, head of X) asking them to choose between two or three options, each with a cost or time figure",
    "status": "raw status notes for a manager that end with something the manager must sign off on",
    "pr": "a pull-request description written from a diff summary, asking a named reviewer to review and approve one of two approaches",
    "exec": "raw notes summarising a long internal report for an executive who must act on its main finding",
    "incident": "raw notes handing an incident over to a named on-call owner who must take a specific step",
}
DOMAINS = ("warehouse automation", "clinic scheduling", "mobile app release", "school bus routing", "bakery chain expansion",
           "municipal water meters", "library catalogue migration", "call-centre staffing", "greenhouse climate control",
           "ferry timetable change", "hospital laundry contract", "open-source licence audit", "farm cooperative pricing",
           "museum ticketing system", "data-centre cooling", "pharmacy stock forecasting", "university timetable tool",
           "food-bank logistics", "bike-share rebalancing", "newsroom publishing tool", "solar roof installation",
           "payroll provider switch", "airport baggage handling", "veterinary clinic software", "city parking sensors",
           "fitness studio booking", "legal document review", "wind-farm maintenance", "textbook print run",
           "restaurant supplier change", "fleet charging depots", "recycling plant sorting", "theatre season budget",
           "language-school onboarding", "chemistry lab inventory")
_lock = threading.Lock()


def ledger(**e):
    now = time.time()
    e = {"ts": int(now), "iso": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **e}
    with _lock, open(D / "ledger.jsonl", "a") as f:
        f.write(json.dumps(e) + "\n")


def call(role, model, system, user, temperature=0.0, **tag):
    """One logged PCSS call -> text; raises RuntimeError (type only, never the key) after R.chat's retries."""
    t = time.time()
    try:
        out = R.chat(model, system, user, temperature=temperature)
        ledger(event="call", role=role, model=model, sec=round(time.time() - t, 1), err="", **tag)
        return out
    except RuntimeError as e:
        ledger(event="call", role=role, model=model, sec=round(time.time() - t, 1), err=str(e)[:80], **tag)
        raise


# ---- deterministic scoring ------------------------------------------------------------------------------------------
MONTHS = dict(january="jan", february="feb", march="mar", april="apr", june="jun", july="jul", august="aug",
              september="sep", sept="sep", october="oct", november="nov", december="dec")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def norm(t):
    """Lowercase; drop $ , markdown marks; unify million/thousand/percent and month names so '$2.4 million' matches '2.4M'."""
    t = t.lower().replace("–", "-").replace("—", "-").replace("‑", "-")
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)
    t = re.sub(r"[$*`_\"']", "", t)
    t = re.sub(r"\bmillion\b", "m", t)
    t = re.sub(r"\bthousand\b", "k", t)
    t = re.sub(r"\bpercent\b", "%", t)
    t = re.sub(r"\b(" + "|".join(MONTHS) + r")\b", lambda m: MONTHS[m.group(1)], t)
    t = re.sub(r"(\d) (m|k|%)(?![a-z])", r"\1\2", t)
    return re.sub(r"\s+", " ", t).strip()


def _numbers(t):
    t = re.sub(r"(?m)^\s*(?:[-*]\s*)?\d+[.)]\s", " ", norm(t))  # numbered-list markers are not figures
    return set(re.findall(r"\d+(?:\.\d+)?", t)) | {w for w in WEEKDAYS if w in t}


def dropped(msg, facts):
    """Literal facts (from the source notes) that the message does not carry, after normalisation."""
    m = norm(msg)
    return [f for f in facts if norm(f) not in m]


def invented(msg, source):
    """Numeric tokens and weekdays in the message that the source notes never contain (a derived figure counts: zero tolerance)."""
    return sorted(_numbers(msg) - _numbers(source))


def words(msg):
    return len(msg.split())


def parse_json(txt):
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except ValueError:
        return None


def paired(a, b, n=10000, seed=1):
    """Mean and 95% percentile-bootstrap CI of the per-scenario paired difference a - b."""
    d = [x - y for x, y in zip(a, b)]
    return sum(d) / len(d), *R.boot(d, n, seed)


# ---- scenarios ------------------------------------------------------------------------------------------------------
def scen(split):
    out = D / f"scenarios_{split}.json"
    if out.exists():
        return print("exists", out)
    n = {"tune": 40, "held": 30}[split]
    other = D / f"scenarios_{'held' if split == 'tune' else 'tune'}.json"
    taken = {(s["kind"], s["domain"]) for s in json.loads(other.read_text())} if other.exists() else set()
    combos = [(k, d) for d in DOMAINS for k in KINDS if (k, d) not in taken]
    rng = random.Random({"tune": 1019, "held": 2019}[split])
    rng.shuffle(combos)
    pick, per = [], {k: 0 for k in KINDS}
    for k, d in combos:  # balanced across kinds
        if per[k] < n // len(KINDS) and len(pick) < n:
            pick.append((k, d)); per[k] += 1
    brief = (D / "prompts/writer_brief.txt").read_text()

    def one(i):
        k, d = pick[i]
        for att in range(4):
            seed = f"{split}{i:02d}-{att}"
            try:
                raw = call("write", WRITER, "You write synthetic test scenarios.", brief.format(kind_desc=KINDS[k], domain=d, seed=seed), 0.9, id=f"{split}{i:02d}", att=att)
            except RuntimeError:
                continue
            j = parse_json(raw)
            if not j or not all(isinstance(j.get(x), str) and j[x].strip() for x in ("prompt", "recipient", "decision", "action", "owner", "deadline", "number", "number_literal", "owner_literal", "deadline_literal")) or not isinstance(j.get("facts"), list):
                continue
            facts = [f for f in dict.fromkeys([j["number_literal"], j["owner_literal"], j["deadline_literal"], *map(str, j["facts"])]) if f.strip()]
            if dropped(j["prompt"], facts) or len(facts) < 4 or len(_numbers(j["prompt"])) < 4:
                continue  # every literal must really occur in the notes: computed, not trusted
            return {"id": f"{split}{i + 1:02d}", "split": split, "kind": k, "domain": d, "prompt": j["prompt"], "recipient": j["recipient"],
                    **{x: j[x] for x in QS}, "facts": facts}
        return None
    with cf.ThreadPoolExecutor(JOBS) as ex:
        res = list(ex.map(one, range(len(pick))))
    ok = [r for r in res if r]
    print(f"{len(ok)}/{len(pick)} scenarios valid")
    out.write_text(json.dumps(ok, indent=1) + "\n")


def load(split):
    return json.loads((D / f"scenarios_{split}.json").read_text())


# ---- run ------------------------------------------------------------------------------------------------------------
def arm_system(arm):
    return (RIVAL if arm == "RIVAL" else D / "prompts" / f"{arm}.txt").read_text()


def cached(p, make):
    if p.exists():
        return p.read_text()
    txt = make()
    R.save(p, txt)
    return txt


def one(split, arm, sc, k):
    base = f"{sc['id']}_{k}"
    try:
        msg = cached(D / "outputs" / split / arm / f"{base}.txt", lambda: call("gen", GENERATOR, arm_system(arm), R.GEN_TASK + sc["prompt"], 0.7, id=sc["id"], arm=arm, k=k))
        for rd in READERS:
            ans = cached(D / "reads" / split / arm / f"{base}_{rd}.json", lambda: call("read", rd, "You answer questions about a message.", (D / "prompts/reader.txt").read_text().format(recipient=sc["recipient"], msg=msg), 0.0, id=sc["id"], arm=arm, k=k))
            cached(D / "grades" / split / arm / f"{base}_{rd}.json", lambda: call("grade", GRADER, "You are a strict, fair grader.", (D / "prompts/grader.txt").read_text().format(answers=ans, **{q: sc[q] for q in QS}), 0.0, id=sc["id"], arm=arm, k=k, reader=rd))
    except RuntimeError as e:
        print("FAIL", split, arm, base, e)


def run(split, arms):
    ledger(event="run_start", split=split, arms=arms)
    jobs = [(split, a, sc, k) for a in arms for sc in load(split) for k in range(SAMPLES)]
    with cf.ThreadPoolExecutor(JOBS) as ex:
        list(ex.map(lambda j: one(*j), jobs))
    ledger(event="run_done", split=split, arms=arms)


# ---- report ---------------------------------------------------------------------------------------------------------
def score(split, arm):
    """Per scenario: accuracy (mean over samples x readers x 5 questions), per-reader accuracy, drop/invent rates, words. A missing record scores 0 and is counted."""
    rows, missing = [], 0
    for sc in load(split):
        acc = {r: [] for r in READERS}; qacc = {q: [] for q in QS}; dr, iv, wd = [], [], []
        for k in range(SAMPLES):
            f = D / "outputs" / split / arm / f"{sc['id']}_{k}.txt"
            msg = f.read_text() if f.exists() else ""
            dr.append(1 if (not msg or dropped(msg, sc["facts"])) else 0)
            iv.append(1 if invented(msg, sc["prompt"]) else 0)
            wd.append(words(msg))
            for r in READERS:
                g = D / "grades" / split / arm / f"{sc['id']}_{k}_{r}.json"
                j = parse_json(g.read_text()) if g.exists() else None
                if not j:
                    missing += 1
                v = [1.0 if j and j.get(q) is True else 0.0 for q in QS]
                acc[r].append(sum(v) / 5)
                for q, x in zip(QS, v):
                    qacc[q].append(x)
        m = lambda x: sum(x) / len(x)
        rows.append(dict(id=sc["id"], kind=sc["kind"], acc=m([x for r in READERS for x in acc[r]]), by_reader={r: m(acc[r]) for r in READERS},
                         by_q={q: m(qacc[q]) for q in QS}, dropped=m(dr), invented=m(iv), words=m(wd)))
    return rows, missing


def report(split, arms, base="V0"):
    S, lines = {}, []
    for a in arms:
        S[a], miss = score(split, a)
        m = lambda key: sum(r[key] for r in S[a]) / len(S[a])
        lines.append(f"{a}: n={len(S[a])} accuracy={m('acc'):.3f} " + " ".join(f"{r}={sum(x['by_reader'][r] for x in S[a]) / len(S[a]):.3f}" for r in READERS)
                     + " | " + " ".join(f"{q}={sum(x['by_q'][q] for x in S[a]) / len(S[a]):.2f}" for q in QS)
                     + f" | dropped_rate={m('dropped'):.3f} invented_rate={m('invented'):.3f} words={m('words'):.0f} missing_grades={miss}")
    for a in arms:
        if a == base:
            continue
        d, lo, hi = paired([r["acc"] for r in S[a]], [r["acc"] for r in S[base]])
        per = " ".join(f"{r}={paired([x['by_reader'][r] for x in S[a]], [x['by_reader'][r] for x in S[base]])[0]:+.3f}" for r in READERS)
        lines.append(f"{a} - {base}: {d:+.3f} 95% CI [{lo:+.3f}, {hi:+.3f}] | by reader {per}")
    txt = "\n".join(lines)
    print(txt)
    (D / f"report_{split}.txt").write_text(txt + "\n")
    (D / f"per_scenario_{split}.json").write_text(json.dumps(S, indent=1) + "\n")


if __name__ == "__main__":
    c, sp, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
    if c == "scen":
        scen(sp)
    elif c == "run":
        run(sp, rest)
    elif c == "report":
        report(sp, rest, os.environ.get("BASE", "V0"))
