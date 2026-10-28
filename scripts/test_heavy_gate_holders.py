#!/usr/bin/env python3
"""heavy_gate.py's HOLD message names the lease holders (pid, kind, age) from the lease files, with no ps/top call."""
import json, os, subprocess, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HG = os.path.join(ROOT, ".claude/skills/agentic-delivery/scripts/heavy_gate.py")
d = tempfile.mkdtemp(prefix="dcr-hg-holders.")
heavy = os.path.join(d, "heavy")
os.makedirs(heavy)
sleepers = [subprocess.Popen(["sleep", "60"]) for _ in range(2)]
try:
    now = int(time.time())
    for p, kind, age in ((sleepers[0], "heavy", 0), (sleepers[1], "train", 600)):
        open(os.path.join(heavy, str(p.pid)), "w").write(f"{p.pid} {now - age} {kind}")
    env = dict(os.environ, PERUN_HEAVY_DIR=heavy, PERUN_GATE_LOAD1="0", PERUN_GATE_CORES="1", PERUN_GATE_FREE_RAM_PCT="60",
               PERUN_POLICY=os.path.join(d, "none.json"), PERUN_HEAVY_HOOK_WAIT_SECS="0")
    open(env["PERUN_POLICY"], "w").write("{}")
    r = subprocess.run([sys.executable, HG], input=json.dumps({"tool_input": {"command": "pytest tests"}, "cwd": "/x"}),
                       env=env, capture_output=True, text=True)
    why = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "heavy-lease-full" in why, why
    assert f"pid {sleepers[0].pid} (heavy, 0m)" in why and f"pid {sleepers[1].pid} (train, 10m)" in why, why
    # exclusive train gate pid is named too; no holders -> no "held by"; a raising holders() still denies
    open(os.path.join(d, "heavy.exclusive"), "w").write(f"{sleepers[0].pid} {now}")
    n = [0]
    def deny(extra="", e=env):
        n[0] += 1  # a distinct command each call: the same one denied 3 times is allowed through by the retry ledger
        r = subprocess.run([sys.executable, "-c", extra + "import runpy,sys; sys.argv=['hg']; runpy.run_path(%r, run_name='__main__')" % HG],
                           input=json.dumps({"tool_input": {"command": f"pytest tests/t{n[0]}"}, "cwd": "/x"}), env=e, capture_output=True, text=True)
        return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert f"train gate pid {sleepers[0].pid}" in deny(), "exclusive holder not named"
    os.unlink(os.path.join(d, "heavy.exclusive"))
    boom = "import sys; sys.path.insert(0, %r); import perun_policy; o = perun_policy._leases; perun_policy._leases = lambda *a: 1/0 if len(a) == 2 else o(*a)\n" % os.path.dirname(HG)
    assert "heavy-lease-full" in (w := deny(boom)) and "held by" not in w, "holders() failure must keep the deny"
    for f in os.listdir(heavy):
        os.unlink(os.path.join(heavy, f))
    ex = dict(env, PERUN_GATE_LOAD1="99")  # busy by load, no lease files: no holders
    assert "held by" not in deny(e=ex)
    print("ok: HOLD message names lease holders")
finally:
    for p in sleepers:
        p.kill()
