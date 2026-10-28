# Registers the peer-lessons batch tests with CI (see the "Per-PR tests" step in ci.yml).
python3 scripts/test_fitness_tick.py
python3 scripts/test_flake_holder.py
python3 scripts/test_finding_guard.py
python3 scripts/test_orphan_allowlist_wired.py
python3 scripts/test_freeze_gate.py
python3 scripts/test_flow_alarm.py
python3 scripts/test_baseline_guard.py
python3 scripts/test_quarantine_ticket_cap.py
python3 scripts/test_prevention_lint.py
python3 -c 'import json,sys; t=json.load(open(".claude/skills/agentic-delivery/templates/operating-layer.settings.json")); c=[h["command"] for e in t["hooks"]["PreToolUse"] for h in e["hooks"]]; sys.exit(0 if all(any(s in x for x in c) for s in ("finding_guard.py", "flow_alarm.py")) else 1)'
