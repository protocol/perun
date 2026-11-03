#!/usr/bin/env python3
"""Evil-twin pass: argv = model, bar file. Prompt = evil-twin lens + packet + draft bar; answer via seat.py (quota-gated)."""
import pathlib, subprocess, sys
H = pathlib.Path(__file__).parent
lens = (H / "root/.claude/skills/idea-critic/scripts/lenses/evil-twin.txt").read_text()
prompt = f"""{lens}

You are attacking a DRAFT definition of "ready" for Perun, a security audit product. Find every way this bar could be
met while the owner's ask is NOT met (a project Perun calls reviewed is still insecure, deps stale, an API call
unprotected, a standard item silently unchecked), every way it can be gamed or measured wrongly, and every gate that
is unmeasurable, unaffordable or never finishes. Ground each point in the packet or the bar text; mark unverified
points. Do not restate the bar.

Reply with ONLY a JSON object:
{{"verdict": "HOLD|REVISE|PASS", "kills": [{{"target": "<gate id or 'missing'>", "failure": "<how it fails>",
"earliest_sign": "<observable>", "tripwire": "<measurable stop rule>", "fix": "<smallest change to the bar>"}}]}}
At most 8 kills, strongest first.

PACKET:
{(H / 'packet.md').read_text()}

DRAFT BAR:
{pathlib.Path(sys.argv[2]).read_text()}
"""
p = subprocess.run([sys.executable, "-I", str(H / "seat.py"), sys.argv[1]], input=prompt, capture_output=True, text=True)
sys.stdout.write(p.stdout)
sys.exit(p.returncode and f"twin: seat failed: {p.stderr.strip()[-300:]}")
