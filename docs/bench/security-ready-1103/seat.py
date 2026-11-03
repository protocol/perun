#!/usr/bin/env python3
"""Council seat via claude -p: prompt on stdin -> answer on stdout. Fails closed (exit 1) when this run's ledger
would pass CAP or the plan-quota reading is missing or >= 0.8. Appends one cost row per call to ledger.jsonl."""
import json, pathlib, subprocess, sys, tempfile, time
CAP, STOP, L = 3.0, 0.8, pathlib.Path(__file__).with_name("ledger.jsonl")
spent = sum(json.loads(x).get("cost", 0) for x in L.read_text().splitlines()) if L.exists() else 0.0
if spent + 0.5 > CAP:
    sys.exit(f"seat: cap ${CAP} reached (spent {spent:.2f})")
p = subprocess.run(["claude", "-p", "--model", sys.argv[1], "--strict-mcp-config", "--no-session-persistence", "--tools", "",
                    "--setting-sources", "", "--max-budget-usd", "0.5", "--output-format", "stream-json", "--verbose"],
                   input=sys.stdin.read(), capture_output=True, text=True, cwd=tempfile.gettempdir(), timeout=600)
txt, cost, util, seen = "", 0.0, 0.0, False
for line in p.stdout.splitlines():
    try:
        j = json.loads(line)
    except ValueError:
        continue
    if j.get("type") == "rate_limit_event":
        ws = (j.get("rate_limit_info") or {}).get("unifiedWindows") or {}
        util, seen = max([util] + [float(v.get("utilization") or 0) for v in ws.values()]), seen or bool(ws)
    elif j.get("type") == "result":
        txt, cost = j.get("result") or "", float(j.get("total_cost_usd") or 0)
with open(L, "a") as f:
    f.write(json.dumps(dict(ts=int(time.time()), model=sys.argv[1], cost=cost, util=util if seen else None)) + "\n")
if not seen or util >= STOP:
    sys.exit(f"seat: quota {'unread' if not seen else util} (stop at {STOP})")
print(txt)
