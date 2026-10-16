#!/usr/bin/env python3
"""comms-quality bench driver (see PREREGISTERED.md). usage: bench.py freeze | verify | scen | run | ablation | report
Reuses the committed harness docs/bench/comms-rubricfree-1016/bench.py (claude -p wrapper with ledger, cap and in-flight
reserve; JSON parse; bootstrap CI; the one-shot generator and the blind judge) and adds a third arm (PLAIN) and the
lint-and-rewrite loop for PERUN. Arms are frozen system prompts under prompts/. Generation: Sonnet, no tools. Judge: Opus,
blind, no criteria, both orders. Hard cap CAP USD over everything in ledger.jsonl; every call also passes --max-budget-usd."""
import concurrent.futures as cf
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

D = Path(__file__).resolve().parent
ROOT = D.parents[2]
OLD = ROOT / "docs/bench/comms-rubricfree-1016"
SKILL = ROOT / ".claude/skills/communication-structure"
spec = importlib.util.spec_from_file_location("old_bench", OLD / "bench.py")
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
sys.path.insert(0, str(SKILL / "scripts"))
import comms_lint  # noqa: E402

CAP, JOBS = 3.0, int(os.environ.get("JOBS", 3))
ARMS = {"PERUN": "perun.txt", "RIVAL": str(OLD / "prompts/rival.txt"), "PLAIN": "plain.txt", "PERUNDRAFT": "perun.txt"}
old.D, old.P, old.CAP, old.ARMS = D, D / "prompts", CAP, ARMS
old.PER_CALL = {"gen": 0.12, "judge": 0.15, "scen": 0.60}  # reserve and --max-budget-usd per call
P = old.P
KIND = {"01": "status", "02": "status", "03": "status", "04": "status", "05": "pr", "06": "pr", "07": "pr", "08": "decision", "09": "decision", "10": "decision"}
PAIRS = (("PERUN", "RIVAL"), ("PERUN", "PLAIN"))
NOTE = re.compile(r"\n+(?:-{3,}\s*\n+)?(?:\*\*)?Notes?\s*:", re.I)
UNCHANGED = {"prompts/gen_task.txt": "prompts/gen_task.txt", "prompts/judge.txt": "prompts/judge.txt"}  # byte-identical to the old harness


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def artifact(txt):
    """The finished text: everything before the trailing note lines."""
    return NOTE.split(txt, maxsplit=1)[0].strip()


def compose():
    return (SKILL / "SKILL.md").read_text() + "\n\n---\nreferences/artifact-templates.md\n---\n\n" + (SKILL / "references/artifact-templates.md").read_text()


def freeze():
    (P / "perun.txt").write_text(compose())
    names = ["PREREGISTERED.md", "bench.py", "prompts/perun.txt", "prompts/plain.txt", "prompts/gen_task.txt", "prompts/judge.txt",
             "prompts/rewrite_task.txt", "prompts/writer_brief.txt", "prompts/seeds.txt"]
    (D / "SHA256-frozen.txt").write_text("".join(f"{sha(D / n)}  {n}\n" for n in names))
    print((D / "SHA256-frozen.txt").read_text())


def verify():
    ok = (P / "perun.txt").read_text() == compose()
    ok &= all(sha(D / n) == sha(OLD / n) for n in UNCHANGED)
    print("perun.txt equals the committed skill text:", (P / "perun.txt").read_text() == compose())
    print("gen_task.txt and judge.txt identical to comms-rubricfree-1016:", all(sha(D / n) == sha(OLD / n) for n in UNCHANGED))
    return 0 if ok else 1


def lint_report(kind, txt):
    res = comms_lint.lint(kind, artifact(txt))
    return res, "\n".join(ln for ln in comms_lint.render(res).splitlines() if ln.startswith("FAIL"))


def gen_perun(sc, arm="PERUN", system_file="perun.txt", rewrite_file="rewrite_task.txt"):
    """Draft with the skill and templates, lint it as the pre-send hook does (no source), rewrite once if below the bar."""
    final, draft = D / "outputs" / arm / f"{sc['id']}.txt", D / "outputs" / (arm + "DRAFT") / f"{sc['id']}.txt"
    if final.exists():
        return
    final.parent.mkdir(parents=True, exist_ok=True)
    draft.parent.mkdir(parents=True, exist_ok=True)
    system = (P / system_file).read_text()
    for attempt in (1, 2):
        txt, err = old.call("gen", (P / "gen_task.txt").read_text() + sc["prompt"], system, f"gen/{arm}/{sc['id']}/{attempt}")
        if not err:
            break
    else:
        return print("GEN FAIL", arm, sc["id"], err)
    draft.write_text(txt)
    res, report = lint_report(KIND[sc["id"]], txt)
    if not res["ok"]:
        prompt = (P / rewrite_file).read_text() + f"\nREQUEST:\n{sc['prompt']}\n\nFIRST DRAFT:\n{txt}\n\nCHECKER REPORT:\n{report}\n"
        t2, err2 = old.call("gen", prompt, system, f"gen/{arm}/{sc['id']}/rewrite")
        txt = t2 if not err2 else txt
    final.write_text(txt)


def explore():
    """EXPLORATORY, post-hoc, not preregistered: the skill and linter as revised after the failed primary run (PERUN2) against
    PLAIN, one verdict per scenario with the order alternating by scenario (not both orders: budget). Descriptive only."""
    (P / "perun2.txt").write_text(compose())
    ARMS["PERUN2"] = "perun2.txt"
    scs = scenarios()
    try:
        with cf.ThreadPoolExecutor(2) as ex:
            list(ex.map(lambda s: gen_perun(s, "PERUN2", "perun2.txt", "rewrite_task2.txt"), scs))
        for i, sc in enumerate(scs):
            old.judge(*(("PERUN2", "PLAIN") if i % 2 == 0 else ("PLAIN", "PERUN2")), sc)
    except old.Cap as e:
        print("STOP", e)
    per = {}
    for i, sc in enumerate(scs):
        f, g = ("PERUN2", "PLAIN") if i % 2 == 0 else ("PLAIN", "PERUN2")
        p = D / "judge" / f"{f}__{g}" / f"{sc['id']}.json"
        if p.exists():
            w = {"1": f, "2": g, "tie": None}[json.loads(p.read_text())["verdict"]]
            per[sc["id"]] = 0.5 if w is None else 1.0 if w == "PERUN2" else 0.0
    v = list(per.values())
    lo, hi = old.boot(v) if v else (None, None)
    res = dict(exploratory=True, x="PERUN2", y="PLAIN", n=len(v), win_rate=round(sum(v) / len(v), 3) if v else None,
               ci95=[round(lo, 3), round(hi, 3)] if v else None, per_scenario=per, objective={a: objective_arm(a) for a in ("PERUN2DRAFT", "PERUN2", "PLAIN")},
               spend_usd_cumulative=round(old.spent(), 4))
    (D / "results-exploratory.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "per_scenario"}, indent=1))


def objective_arm(arm):
    rows = [(sc["id"], D / "outputs" / arm / f"{sc['id']}.txt") for sc in scenarios()]
    rows = [(i, p.read_text()) for i, p in rows if p.exists()]
    if not rows:
        return None
    w = sorted(len(artifact(t).split()) for _, t in rows)
    stand_ins = sum(bool(re.search(r"owner unassigned|no deadline|not stated|not specified", t, re.I)) for _, t in rows)
    return dict(n=len(rows), pass_lint=sum(comms_lint.lint(KIND[i], artifact(t))["ok"] for i, t in rows), words_median=w[len(w) // 2], with_stand_in_text=stand_ins)


def scenarios():
    return json.loads((D / "scenarios.json").read_text())


def run():
    scs = scenarios()
    try:
        with cf.ThreadPoolExecutor(JOBS) as ex:
            list(ex.map(gen_perun, scs))
            list(ex.map(lambda t: old.gen(*t), [(a, s) for a in ("RIVAL", "PLAIN") for s in scs]))
        with cf.ThreadPoolExecutor(JOBS) as ex:
            list(ex.map(lambda t: old.judge(*t), [(f, g, sc) for sc in scs for x, y in PAIRS for f, g in ((x, y), (y, x))]))
    except old.Cap as e:
        print("STOP", e)
    report()


def ablation():
    """Secondary, descriptive only: PERUN's first draft (before the lint loop) against PLAIN. Runs only below ABLATION_MAX spend."""
    if old.spent() > 2.0:
        return print("ablation skipped: spend", round(old.spent(), 3), "> 2.0")
    scs = scenarios()
    try:
        with cf.ThreadPoolExecutor(JOBS) as ex:
            list(ex.map(lambda t: old.judge(*t), [(f, g, sc) for sc in scs for f, g in (("PERUNDRAFT", "PLAIN"), ("PLAIN", "PERUNDRAFT"))]))
    except old.Cap as e:
        print("STOP", e)
    report()


def pair_result(x, y):
    per, splits = {}, 0
    for sc in scenarios():
        s = []
        for f, g in ((x, y), (y, x)):
            p = D / "judge" / f"{f}__{g}" / f"{sc['id']}.json"
            if not p.exists():
                break
            w = {"1": f, "2": g, "tie": None}[json.loads(p.read_text())["verdict"]]
            s.append(0.5 if w is None else 1.0 if w == x else 0.0)
        if len(s) == 2:
            per[sc["id"]] = sum(s) / 2
            splits += s[0] != s[1]
    v = list(per.values())
    res = dict(x=x, y=y, n=len(v), win_rate=round(sum(v) / len(v), 3) if v else None, order_splits=splits, per_scenario=per)
    if v:
        lo, hi = old.boot(v)
        res.update(ci95=[round(lo, 3), round(hi, 3)], verdict="PASS" if lo > 0.5 else "FAIL")
    return res


def objective():
    """Judge-free numbers per arm: share of outputs that clear comms_lint for their kind, and median words of the finished text."""
    out = {}
    for arm in ("PERUN", "PERUNDRAFT", "RIVAL", "PLAIN"):
        rows = [(sc["id"], (D / "outputs" / arm / f"{sc['id']}.txt")) for sc in scenarios()]
        rows = [(i, p.read_text()) for i, p in rows if p.exists()]
        if rows:
            ok = [comms_lint.lint(KIND[i], artifact(t))["ok"] for i, t in rows]
            w = sorted(len(artifact(t).split()) for _, t in rows)
            out[arm] = dict(n=len(rows), pass_lint=sum(ok), words_median=w[len(w) // 2])
    return out


def report():
    res = {p[0] + "_vs_" + p[1]: pair_result(*p) for p in PAIRS + (("PERUNDRAFT", "PLAIN"),) if (D / "judge" / f"{p[0]}__{p[1]}").exists()}
    res["objective_not_judged"] = objective()
    res["spend_usd_cumulative"] = round(old.spent(), 4)
    res["bootstrap"] = "10000 resamples, seed 1, percentile, over scenarios"
    (D / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: ({a: b for a, b in v.items() if a != "per_scenario"} if isinstance(v, dict) and "per_scenario" in v else v) for k, v in res.items()}, indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "scen":
        old.scen()
    else:
        sys.exit({"freeze": freeze, "verify": verify, "run": run, "ablation": ablation, "report": report, "explore": explore}[cmd]() or 0)
