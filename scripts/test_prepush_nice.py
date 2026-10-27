#!/usr/bin/env python3
"""The pre-push gate runs under `nice -n 19`, outermost, and the stage exit codes 75/124 survive it."""
import re, subprocess
s = open(".claude/skills/deep-code-review/templates/pre-push-verify.sh").read()
m = re.search(r'gate_cmd=\(nice -n 19 "\$\{gate_cmd\[@\]\}"\)', s)
assert m, "pre-push gate is not wrapped in nice -n 19"
assert m.start() > s.index("gate_cmd=(python3"), "nice must wrap the stage_run.py wrapper"
assert m.start() < s.index('"${gate_cmd[@]}" </dev/null'), "nice must be set before the gate runs"
for rc in (75, 124):  # stub gate: stage_run's DEFER and timeout codes must reach the case statement unchanged
    assert subprocess.run(["nice", "-n", "19", "sh", "-c", f"exit {rc}"]).returncode == rc
print("ok: pre-push gate runs under nice -n 19; rc 75/124 survive")
