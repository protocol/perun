#!/usr/bin/env python3
"""Exec-skill superiority bench driver (see PREREGISTERED.md). No Anthropic calls; all models run on PCSS.
usage: bench.py scen SKILL | run SKILL ARM SPLIT | report SKILL ARM SPLIT
SKILL in agentic-ceo idea-critic business-ops growth-analytics positioning; ARM = PERUN_v0 / PERUN_v1 (prompts/perun_<SKILL>_<v>.txt);
SPLIT in tune / heldout. RIVAL (prompts/rival_<SKILL>.txt) is generated once per scenario and shared by every ARM.
Reads PCSS_KEY from PCSS_ENV (default: the repo-root .env); the key is never printed or logged."""
import concurrent.futures as cf, json, os, random, sys, time, urllib.request
from pathlib import Path

D = Path(__file__).resolve().parent
P = D / "prompts"
URL = "https://llm.hpc.psnc.pl/v1/chat/completions"
GEN, JUDGE, TIE, WRITER = "Qwen3.5-397B-A17B", "DeepSeek-V4-Flash", "GLM-5.2", "gpt-oss_120b"
SKILLS = ["agentic-ceo", "idea-critic", "business-ops", "growth-analytics", "positioning"]
JOBS = int(os.environ.get("JOBS", 6))


def key():
    f = Path(os.environ.get("PCSS_ENV", "/Users/remiantczak/Desktop/deep-code-review/.env"))
    return next(l.split("=", 1)[1].strip().strip("\"'") for l in f.read_text().splitlines() if l.startswith("PCSS_KEY="))


KEY = key()


def call(model, system, user, tag, max_tokens=3000, temp=0.7, no_think=False):
    """One chat completion with 4 attempts. Returns text ('' on failure). Ledger line per call (no key, no text)."""
    body = dict(model=model, max_tokens=max_tokens, temperature=temp,
                messages=([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}])
    if no_think:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    for att in range(4):
        t, err, txt, use = time.time(), "", "", {}
        try:
            r = urllib.request.Request(URL, json.dumps(body).encode(), {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
            j = json.load(urllib.request.urlopen(r, timeout=600))
            txt, use = (j["choices"][0]["message"].get("content") or "").strip(), j.get("usage", {})
            err = "" if txt else "empty"
        except Exception as e:  # noqa: BLE001 - network/HTTP errors are retried and logged by type only
            err = type(e).__name__
        with open(D / "ledger.jsonl", "a") as f:
            f.write(json.dumps(dict(tag=tag, model=model, att=att, sec=round(time.time() - t, 1), err=err, usage=use)) + "\n")
        if txt:
            return txt
        time.sleep(3 * (att + 1))
    return ""


def jparse(txt):
    s = txt.strip()
    if "{" in s and "}" in s:
        try:
            return json.loads(s[s.index("{"): s.rindex("}") + 1])
        except ValueError:
            pass
    return None


def scen(skill):
    """30 scenarios per skill: seed list rotated by 6*skill index; first 10 = tune, last 20 = heldout (fixed before any generation)."""
    out = D / "scenarios" / f"{skill}.json"
    if out.exists():
        return print("cached", out)
    seeds = (P / "seeds.txt").read_text().strip().splitlines()
    r = 6 * SKILLS.index(skill)
    seeds = seeds[r:] + seeds[:r]
    sysm = (P / "writer_common.txt").read_text()
    brief = (P / f"writer_{skill}.txt").read_text()

    def one(i):
        for a in range(3):
            t = call(WRITER, sysm, f"{brief}\nSetting: {seeds[i]}\nWrite the scenario now.", f"scen/{skill}/{i}", 4000, 0.9)
            if 100 <= len(t.split()) <= 280:
                return dict(id=f"{i + 1:02d}", split="tune" if i < 10 else "heldout", setting=seeds[i], prompt=t)
        raise SystemExit(f"scenario {skill}/{i} failed word-count after 3 tries")

    with cf.ThreadPoolExecutor(JOBS) as ex:
        arr = list(ex.map(one, range(30)))
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(arr, indent=1) + "\n")


def load(skill, split):
    return [s for s in json.loads((D / "scenarios" / f"{skill}.json").read_text()) if s["split"] == split]


def gen(skill, arm, sc):
    p = D / "outputs" / skill / arm / f"{sc['id']}.txt"
    if p.exists():
        return
    f = P / (f"rival_{skill}.txt" if arm == "RIVAL" else f"perun_{skill}_{arm.split('_')[1]}.txt")
    p.parent.mkdir(parents=True, exist_ok=True)
    t = call(GEN, f.read_text(), (P / "gen_task.txt").read_text() + sc["prompt"], f"gen/{skill}/{arm}/{sc['id']}", 3000, 0.7, True)
    p.write_text(t) if t else print("GEN FAIL", skill, arm, sc["id"])


def one_judge(model, sc, first, second, tag, skill):
    a, b = (D / "outputs" / skill / x / f"{sc['id']}.txt" for x in (first, second))
    prompt = f"REQUEST:\n{sc['prompt']}\n\n=== Response 1 ===\n{a.read_text()}\n\n=== Response 2 ===\n{b.read_text()}\n"
    for _ in range(2):
        j = jparse(call(model, (P / "judge.txt").read_text(), prompt, tag, 600, 0.0, no_think=model == TIE))  # ADDENDUM-1: GLM thinking off
        if isinstance(j, dict) and j.get("verdict") in ("1", "2", "tie"):
            return dict(first=first, second=second, winner={"1": first, "2": second, "tie": "tie"}[j["verdict"]], reason=j.get("reason", ""))
    return None


def judge(skill, arm, sc):
    """DeepSeek twice (randomized which arm is Response 1, then swapped). Agreement on one arm decides; a split, a tie or a
    failure goes to one GLM-5.2 call with an independently randomized order. Cached under judge/<skill>/<arm>/<id>.json."""
    p = D / "judge" / skill / arm / f"{sc['id']}.json"
    if p.exists():
        return
    if not all((D / "outputs" / skill / x / f"{sc['id']}.txt").exists() for x in (arm, "RIVAL")):
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(f"{skill}-{arm}-{sc['id']}")
    o = [arm, "RIVAL"]
    rng.shuffle(o)
    d = [one_judge(JUDGE, sc, o[0], o[1], f"judge/{skill}/{arm}/{sc['id']}/ds1", skill),
         one_judge(JUDGE, sc, o[1], o[0], f"judge/{skill}/{arm}/{sc['id']}/ds2", skill)]
    w = [x["winner"] if x else "fail" for x in d]
    rec = dict(deepseek=d, tiebreak=None)
    if w[0] == w[1] and w[0] in (arm, "RIVAL"):
        rec["final"] = w[0]
    else:
        o2 = [arm, "RIVAL"]
        rng.shuffle(o2)
        g = one_judge(TIE, sc, o2[0], o2[1], f"judge/{skill}/{arm}/{sc['id']}/glm", skill)
        rec["tiebreak"], rec["final"] = g, (g["winner"] if g else "tie")
    p.write_text(json.dumps(rec, indent=1) + "\n")


def boot(vals, n=10000, seed=1):
    rng, m = random.Random(seed), len(vals)
    bs = sorted(sum(vals[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return bs[int(0.025 * n)], bs[int(0.975 * n) - 1]


def report(skill, arm, split):
    """Score per scenario = 1 (Perun arm final winner), 0.5 (tie), 0 (RIVAL). PASS only if bootstrap 95% CI lower bound > 0.5 and n >= 20."""
    per, ds_split, tb = {}, 0, 0
    for sc in load(skill, split):
        p = D / "judge" / skill / arm / f"{sc['id']}.json"
        if p.exists():
            r = json.loads(p.read_text())
            per[sc["id"]] = {arm: 1.0, "RIVAL": 0.0}.get(r["final"], 0.5)
            tb += r["tiebreak"] is not None
    v = list(per.values())
    res = dict(skill=skill, arm=arm, split=split, n=len(v), win_rate=round(sum(v) / len(v), 3) if v else None,
               tiebreak_calls=tb, per_scenario=per, bootstrap="10000 resamples, seed 1, percentile, over scenarios")
    if v:
        lo, hi = boot(v)
        res.update(ci95=[round(lo, 3), round(hi, 3)], verdict="PASS" if lo > 0.5 and len(v) >= 20 else "FAIL")
    (D / f"results-{skill}-{arm}-{split}.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in res if k != "per_scenario"}))


def run(skill, arm, split):
    scs = load(skill, split)
    with cf.ThreadPoolExecutor(JOBS) as ex:
        list(ex.map(lambda t: gen(skill, *t), [(a, s) for a in (arm, "RIVAL") for s in scs]))
    with cf.ThreadPoolExecutor(JOBS) as ex:
        list(ex.map(lambda s: judge(skill, arm, s), scs))
    report(skill, arm, split)


if __name__ == "__main__":
    c, a = sys.argv[1], sys.argv[2:]
    {"scen": scen, "run": run, "report": report}[c](*a)
