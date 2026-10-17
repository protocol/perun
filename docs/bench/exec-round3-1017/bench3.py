#!/usr/bin/env python3
"""Round 3 driver (see PREREGISTERED.md). Reuses ../exec-1017/bench.py (calls, bootstrap) and bench2.py (both-order three-judge majority) with
this directory as the output root. No Anthropic calls; everything runs on PCSS. PCSS_ENV must point at a file holding PCSS_KEY.
usage: bench3.py scen SKILL | run SKILL ARM SPLIT | report SKILL ARM SPLIT
SKILL in agentic-ceo idea-critic; SPLIT = tune (old scenarios 01-10) or h3 (scenarios3/<skill>-h3.json, 40 fresh scenarios h01-h40).
ARM = PERUN_<variant>: prompt from prompts/ here, else ../exec-1017/prompts/. RIVAL generations are made once per scenario."""
import concurrent.futures as cf, json, shutil, sys
from pathlib import Path

H = Path(__file__).resolve().parent
sys.path.insert(0, str(H.parent / "exec-1017"))
import bench as b
import bench2 as b2

OLD = b.D
b.D = b2.D = D = H
SKILLS = ["agentic-ceo", "idea-critic"]


def load(skill, split):
    if split == "tune":
        return [s for s in json.loads((OLD / "scenarios" / f"{skill}.json").read_text()) if s["split"] == "tune"]
    return json.loads((D / "scenarios3" / f"{skill}-h3.json").read_text())


def scen(skill):
    out = D / "scenarios3" / f"{skill}-h3.json"
    if out.exists():
        return print("cached", out)
    seeds = (D / "prompts" / "seeds3.txt").read_text().strip().splitlines()
    seeds = seeds[20 * SKILLS.index(skill):] + seeds[:20 * SKILLS.index(skill)]
    sysm, brief = (OLD / "prompts" / "writer_common.txt").read_text(), (OLD / "prompts" / f"writer_{skill}.txt").read_text()

    def one(i):
        for _ in range(3):
            t = b.call(b.WRITER, sysm, f"{brief}\nSetting: {seeds[i]}\nWrite the scenario now.", f"scen3/{skill}/{i}", 4000, 0.9)
            if 100 <= len(t.split()) <= 280:
                return dict(id=f"h{i + 1:02d}", split="h3", setting=seeds[i], prompt=t)
        raise SystemExit(f"scenario {skill}/{i} failed word-count after 3 tries")

    with cf.ThreadPoolExecutor(b.JOBS) as ex:
        arr = list(ex.map(one, range(40)))
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(arr, indent=1) + "\n")


def gen(skill, arm, sc):
    p = D / "outputs" / skill / arm / f"{sc['id']}.txt"
    if p.exists():
        return
    name = f"rival_{skill}.txt" if arm == "RIVAL" else f"perun_{skill}_{arm.split('_')[1]}.txt"
    f = D / "prompts" / name
    f = f if f.exists() else OLD / "prompts" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    t = b.call(b.GEN, f.read_text(), (OLD / "prompts" / "gen_task.txt").read_text() + sc["prompt"], f"gen3/{skill}/{arm}/{sc['id']}", 3000, 0.7, True)
    p.write_text(t) if t else print("GEN FAIL", skill, arm, sc["id"])


def run(skill, arm, split):
    if split == "tune":  # reuse the round-1 rival generations on the tune scenarios
        for s in load(skill, "tune"):
            q = D / "outputs" / skill / "RIVAL" / f"{s['id']}.txt"
            q.parent.mkdir(parents=True, exist_ok=True)
            if not q.exists():
                shutil.copy(OLD / "outputs" / skill / "RIVAL" / f"{s['id']}.txt", q)
    b2.run(skill, arm, split)


b.gen = gen
b2.load = load
if __name__ == "__main__":
    c, a = sys.argv[1], sys.argv[2:]
    {"scen": scen, "run": run, "report": b2.report}[c](*a)
