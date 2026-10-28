#!/usr/bin/env python3
"""host_accept.py — merge-host acceptance checklist: a host is not accepted until all three recovery properties are verified.

(a) reset: an operator can reset the host with a command that needs no extra IAM/permissions beyond what the operator already holds.
(b) auto-reset: the host resets itself after missed heartbeats, with nobody watching.
(c) mem-caps: per-slice (per lane/test slice) memory caps are set AND memory is reserved for sshd and the agent session, so a runaway
    slice cannot lock out the way back in.
Input: `--file` (default .claude/host-accept.json): {"operator_reset": {"verified": true, "evidence": "runbook step or drill log ref",
"date": "2026-01-02"}, "auto_reset": {...same...}, "mem_caps": {...same..., "reserved_mb": 1024}}. A property counts only with `"verified": true`
(JSON true, not "yes"), a non-blank string `evidence` and an ISO `date` not in the future; mem_caps also needs an integer reserved_mb > 0.
`--base REF` reads the file from REF (git show) so a PR cannot attest its own host. train_land.sh runs this (exit 2 on rc != 0) whenever the
base branch carries the file. Output: `ACCEPTED`, or one `NOT-ACCEPTED <property>` per failing property (exit 1). Fail closed: a missing or
unreadable file or a non-object entry exits 2. Read-only; it records an attestation, it does not probe the host (see host_probe.py).
"""
import argparse
import datetime
import json
import subprocess
import sys


def sound(p):
    e = p.get("evidence")
    return p.get("verified") is True and isinstance(e, str) and e.strip() != "" and datetime.date.fromisoformat(p["date"]) <= datetime.date.today()


def failing(cfg):
    bad = [k for k in ("operator_reset", "auto_reset", "mem_caps") if not sound(cfg[k])]
    r = cfg["mem_caps"].get("reserved_mb")
    if "mem_caps" not in bad and not (isinstance(r, int) and not isinstance(r, bool) and r > 0):
        bad.append("mem_caps")
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", default=".claude/host-accept.json")
    ap.add_argument("--base")
    a = ap.parse_args(argv)
    try:
        raw = subprocess.run(["git", "show", f"{a.base}:{a.file}"], capture_output=True, text=True, check=True).stdout if a.base else open(a.file).read()
        bad = failing(json.loads(raw))
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError, TypeError, AttributeError) as e:
        print(f"host_accept: bad input: {e!r}", file=sys.stderr)
        return 2
    print("\n".join(f"NOT-ACCEPTED {k}" for k in bad) if bad else "ACCEPTED")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
