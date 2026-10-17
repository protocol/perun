#!/usr/bin/env python3
"""Round 4 driver, idea-critic only (see PREREGISTERED.md). Reuses ../exec-1017/bench.py (calls, bootstrap) and bench2.py (three judges, both orders,
strict agreement, majority) with this directory as the output root. PCSS only; PCSS_ENV must point at a file holding PCSS_KEY (never printed).
usage: bench4.py scen | rival SPLIT | run ARM SPLIT | report ARM SPLIT        SPLIT = tune (old scenarios 01-10) or h4 (scenarios4/, h01-h40)
ARM = PERUN_<variant> (prompts/perun_idea-critic_<variant>.txt). `rival` generates each RIVAL answer exactly once, before any arm runs, and
freezes its hashes; `run` refuses to start if a RIVAL file is missing or changed (this removes the round-3 double-generation race)."""
import concurrent.futures as cf, hashlib, json, shutil, subprocess, sys, tempfile
from pathlib import Path

H = Path(__file__).resolve().parent
sys.path.insert(0, str(H.parent / "exec-1017"))
import bench as b
import bench2 as b2

OLD = b.D
b.D = b2.D = D = H
SK = "idea-critic"
ROOT = H.parents[2]


def load(skill, split):
    if split == "tune":
        return [s for s in json.loads((OLD / "scenarios" / f"{skill}.json").read_text()) if s["split"] == "tune"]
    return json.loads((D / "scenarios4" / f"{skill}-h4.json").read_text())


def clean(text):
    """Privacy screen: the repo's own gate with the committed and local banlists. True when no pattern hits."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "s.txt").write_text(text)
        return subprocess.run(["bash", str(ROOT / "scripts/ci-gates.sh"), "privacy", "--banlist", str(ROOT / ".banlist.txt"), d],
                              capture_output=True).returncode == 0


def scen():
    out = D / "scenarios4" / f"{SK}-h4.json"
    if out.exists():
        return print("cached", out)
    seeds = (D / "prompts" / "seeds4.txt").read_text().strip().splitlines()
    sysm, brief = (OLD / "prompts" / "writer_common.txt").read_text(), (OLD / "prompts" / f"writer_{SK}.txt").read_text()

    def one(i):
        for _ in range(4):
            t = b.call(b.WRITER, sysm, f"{brief}\nSetting: {seeds[i]}\nWrite the scenario now.", f"scen4/{i}", 4000, 0.9)
            if 100 <= len(t.split()) <= 280 and clean(t):
                return dict(id=f"h{i + 1:02d}", split="h4", setting=seeds[i], prompt=t)
        raise SystemExit(f"scenario {i} failed word-count or privacy screen after 4 tries")

    with cf.ThreadPoolExecutor(b.JOBS) as ex:
        arr = list(ex.map(one, range(len(seeds))))
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(arr, indent=1) + "\n")


def gen(skill, arm, sc):
    p = D / "outputs" / skill / arm / f"{sc['id']}.txt"
    if p.exists():
        return
    f = D / "prompts" / f"perun_{skill}_{arm.split('_')[1]}.txt" if arm != "RIVAL" else OLD / "prompts" / f"rival_{skill}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    t = b.call(b.GEN, f.read_text(), (OLD / "prompts" / "gen_task.txt").read_text() + sc["prompt"], f"gen4/{skill}/{arm}/{sc['id']}", 3000, 0.7, True)
    p.write_text(t) if t else print("GEN FAIL", skill, arm, sc["id"])


def sha(split):
    return {s["id"]: hashlib.sha256((D / "outputs" / SK / "RIVAL" / f"{s['id']}.txt").read_bytes()).hexdigest() for s in load(SK, split)}


def rival(split):
    scs = load(SK, split)
    for s in scs:  # tune: reuse the round-1 RIVAL generation (made once, shared by every arm since)
        q = D / "outputs" / SK / "RIVAL" / f"{s['id']}.txt"
        q.parent.mkdir(parents=True, exist_ok=True)
        if split == "tune" and not q.exists():
            shutil.copy(OLD / "outputs" / SK / "RIVAL" / f"{s['id']}.txt", q)
    with cf.ThreadPoolExecutor(b.JOBS) as ex:
        list(ex.map(lambda s: gen(SK, "RIVAL", s), scs))
    (D / f"RIVAL-sha256-{split}.json").write_text(json.dumps(sha(split), indent=1) + "\n")


def run(arm, split):
    f = D / f"RIVAL-sha256-{split}.json"
    assert f.exists() and json.loads(f.read_text()) == sha(split), "RIVAL files missing or changed since `rival` froze them"
    b2.run(SK, arm, split)


b.gen = gen
b2.load = load
if __name__ == "__main__":
    c, a = sys.argv[1], sys.argv[2:]
    {"scen": lambda: scen(), "rival": rival, "run": lambda *x: run(*x), "report": lambda *x: b2.report(SK, *x)}[c](*a)
