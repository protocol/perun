"""Probe: one REAL-arm review with stream-json; records which files the reviewer read (proves the skill was loaded)."""
import json, shutil, subprocess, sys
from pathlib import Path
sys.argv = ["probe"]
import driver as d

w = d.ws("lo-nth-int-wrap", "REAL")
r = subprocess.run(["claude", "-p", "--model", "claude-sonnet-5-5", "--setting-sources", "project,local", "--strict-mcp-config",
                    "--no-session-persistence", *d.TOOLS, "--output-format", "stream-json", "--verbose"],
                   input=d.bc.PERUN, capture_output=True, text=True, cwd=w, timeout=900)
shutil.rmtree(w, ignore_errors=True)
tools, cost = [], 0.0
for l in r.stdout.splitlines():
    try:
        e = json.loads(l)
    except ValueError:
        continue
    if e.get("type") == "assistant":
        tools += [(c["name"], str(c["input"].get("file_path") or c["input"].get("pattern"))[-70:]) for c in e["message"]["content"] if c["type"] == "tool_use"]
    if e.get("type") == "result":
        cost = e.get("total_cost_usd", 0)
(d.D / "probe-result.json").write_text(json.dumps(dict(tools=tools, cost=cost), indent=1))
print(len(tools), cost)
