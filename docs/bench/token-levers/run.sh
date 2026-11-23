#!/usr/bin/env bash
# Offline, free, deterministic: run token_report.py on the synthetic fixture and assert the levers it finds, their order and amounts.
# Pinned numbers come from the fixture arithmetic (see gen.py, overlay.py); if token_report's estimators change on purpose, rerun and update them here.
# The "150" in the lane-cap lever name is read from this repo's shipped template (agentic-delivery/templates/operating-layer.settings.json, LANE_TOOL_CAP); run from a checkout that has it.
# Part 1 is the frozen session alone. Part 2 uses overlay.py variants: `fire` (big Bash/Read/MCP results, 112 KB CLAUDE.md) and `quiet` (results at the 10000-char floor, 2 KB CLAUDE.md).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
python3 -I - "$here" "$here/../../../.claude/skills/agentic-ceo/scripts/token_report.py" <<'PY'
import json, os, subprocess, sys, tempfile
here, report = sys.argv[1:3]

with tempfile.TemporaryDirectory() as tmp:
    cfg, empty = f"{tmp}/cfg", f"{tmp}/empty"  # empty user config and project: no real CLAUDE.md can leak into the numbers
    os.makedirs(cfg), os.makedirs(empty)
    env = {**os.environ, "CLAUDE_CONFIG_DIR": cfg}

    def run(session, project, *flags):
        return subprocess.run([sys.executable, report, "--session", session, "--project", project, *flags],
                              check=True, capture_output=True, text=True, env=env).stdout

    def levers(r):
        return [(x["lever"], x["saving_ie"], x["share_of_session_ie"]) for x in r["lever_ranking"]]

    # Part 1: frozen session, four levers.
    r = json.loads(run(f"{here}/session.jsonl", empty, "--json"))
    rank = levers(r)
    want = [("pin main cache to 1h", 1284000.0, 0.3526),
            ("lower LANE_TOOL_CAP below 150", 611493.75, 0.1679),
            ("auto-compact at 200000", 217575.0, 0.0597),
            ("orchestrator tier", None, None)]
    assert rank == want, f"lever ranking drifted:\n got  {rank}\n want {want}"
    i, a, t = r["idle_rewrites"], r["auto_compact"], r["lane_tail"]
    assert (i["idle_rewrite_share"], i["idle_rewrite_saving_share_of_main_ie"]) == (0.8514, 0.5069), i
    assert (a["compactions"], a["saving_share_of_main_ie"]) == (1, 0.0859), a
    assert (t["lanes_over_shipped_cap"], t["tail_share_over_shipped_cap"], t["p90_tool_calls"]) == (1, 0.5515, 600), t
    assert r["orchestration_flag"] and r["subagents_count"] == 4, "orchestration flag or lane count drifted"
    assert r["tool_results"]["count"] == 0 and r["startup_files"] == [], "frozen session must have no tool results or startup files"
    assert "Top levers (est. upper-bound saving, not a bill" in run(f"{here}/session.jsonl", empty), "frozen session text report lost its Top levers block"

    # Part 2: tool_results and startup levers, each fires once and stays quiet once.
    subprocess.run([sys.executable, f"{here}/overlay.py", tmp], check=True)
    fire, quiet = f"{tmp}/fire", f"{tmp}/quiet"
    f = json.loads(run(f"{fire}/session.jsonl", f"{fire}/project", "--json"))
    q = json.loads(run(f"{quiet}/session.jsonl", f"{quiet}/project", "--json"))
    ft, qt = f["tool_results"], q["tool_results"]
    # fire: one 150000-char Bash result (140000 past the cap), a 9999-char one below the floor, one Read, one MCP result
    assert (ft["count"], ft["chars"]) == (3, 185000), ft
    assert {k: (v["count"], v["chars"]) for k, v in ft["by_tool"].items()} == {"bash": (1, 150000), "read": (1, 20000), "other": (1, 15000)}, ft
    assert (ft["by_tool"]["bash"]["carry_ie_upper"], ft["bash_share_of_session_ie"], ft["clamped"]) == (203000.0, 0.0557, False), ft
    assert (qt["count"], qt["by_tool"]["bash"]["carry_ie_upper"]) == (0, 0.0), qt  # results at or below 10000 chars are not over the floor
    assert levers(f) == [("pin main cache to 1h", 1284000.0, 0.3526), ("lower LANE_TOOL_CAP below 150", 611493.75, 0.1679),
                         ("auto-compact at 200000", 217575.0, 0.0597), ("cap Bash output with bashOutputMaxChars", 203000.0, 0.0557),
                         ("trim CLAUDE.md (estimate: 50% of its cost)", 190400.0, 0.0523), ("orchestrator tier", None, None)], levers(f)
    assert levers(q) == want, levers(q)
    # startup: the 112 KB file dominates lane startup, so the remainder is tiny; the 2 KB file leaves the remainder dominant
    fr, qr = f["startup_remainder"], q["startup_remainder"]
    assert (f["startup_files"][0]["tokens_est"], f["startup_files"][0]["ie_upper"]) == (28000, 380800.0), f["startup_files"]
    assert (q["startup_files"][0]["tokens_est"], q["startup_files"][0]["share_of_session_ie"]) == (500, 0.0019), q["startup_files"]
    assert (fr["share_of_startup"], fr["share_of_lane_ie"]) == (0.0018, 0.0006), fr
    assert (qr["share_of_startup"], qr["share_of_lane_ie"]) == (0.9822, 0.3379), qr
    # the printed report: lever lines present when fired, absent when quiet; Read/MCP are info lines only; no doubled "(estimate)"
    ftxt, qtxt = run(f"{fire}/session.jsonl", f"{fire}/project"), run(f"{quiet}/session.jsonl", f"{quiet}/project")
    for need in ("Lever: cap Bash output", "Lever: trim or split CLAUDE.md", "Large Read results (1, 20000 chars)", "Large non-Bash, non-Read results (1, 15000 chars)"):
        assert need in ftxt and need not in qtxt, need
    assert "Lever: the remainder dominates lane startup" in qtxt and "Lever: the remainder dominates lane startup" not in ftxt
    assert "Tool results over" not in qtxt
    trim = next(x for x in ftxt.splitlines() if "trim CLAUDE.md (estimate:" in x and "input-eq" in x)
    assert trim.count("(estimate") == 1, trim

print("token-levers: ok (4 levers, ranked; " + ", ".join(f"{n} {s}" for n, _, s in rank if s) + " of session input-eq; "
      "overlay: bashOutputMaxChars 0.0557 and CLAUDE.md trim 0.0523 fire, quiet at the floor; remainder fires only with the small CLAUDE.md)")
PY
