#!/usr/bin/env python3
"""A watchdog or budget must be shorter than the hard timeout it pre-empts.

Checks every workflow file: each step `timeout-minutes` and each inline `timeout N`
(seconds) is below its job's `timeout-minutes`, and the heavy-lease wait default is below
the merge_train per-gate timeout. A budget at or above its ceiling never fires first.
"""
import glob, re, sys

fails = []
n_inner = 0
job_mins = []
for wf in glob.glob(".github/workflows/*.yml"):
    job, jt, inner = None, None, []  # inner: (what, seconds)
    in_jobs = False
    def close():
        if job and jt is None:
            fails.append(f"{wf} job {job}: no timeout-minutes")
        for what, secs in inner:
            if jt is not None and secs >= jt * 60:
                fails.append(f"{wf} job {job}: {what} {secs}s >= job timeout {jt}m")
    for line in open(wf):
        if re.match(r"^jobs:", line):
            in_jobs = True
        elif re.match(r"^\S", line):
            in_jobs = False
        m = in_jobs and re.match(r"^  ([\w-]+):\s*$", line)
        if m:
            close(); job, jt, inner = m.group(1), None, []
            continue
        m = re.match(r"^(\s+)timeout-minutes:\s*(\d+)", line)
        if m:
            if len(m.group(1)) == 4:
                jt = int(m.group(2)); job_mins.append(jt)
            else:
                inner.append(("step timeout-minutes", int(m.group(2)) * 60))
        if not line.lstrip().startswith("#"):
            for n in re.findall(r"\btimeout (\d+) ", line):
                inner.append(("inline timeout", int(n)))
                n_inner += 1
    close()

if not n_inner:
    fails.append("no inline `timeout N` found (parser drift?)")

if not job_mins:
    fails.append("no job timeout-minutes found (parser drift?)")
def dflt(path, pat):
    m = re.search(pat, open(path).read())
    if not m:
        fails.append(f"{path}: default not found for {pat}")
    return float(m.group(1)) if m else None

S = ".claude/skills/agentic-delivery/scripts/"
wait = dflt(S + "job_lease.py", r'"--timeout".*?default=([\d.]+)')
gate = dflt(S + "merge_train.py", r'"--timeout".*?default=(\d+)')
if wait is not None and gate is not None and wait >= gate:
    fails.append(f"heavy-lease wait {wait}s >= merge_train gate timeout {gate}s")

print("\n".join(fails) or f"ok: budgets below timeouts ({len(job_mins)} jobs)")
sys.exit(1 if fails else 0)
