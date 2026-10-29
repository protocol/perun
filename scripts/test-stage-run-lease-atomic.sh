#!/usr/bin/env bash
# stage_run.stamp rewrites the lease while the stage already runs; the rewrite must be atomic. A truncate-then-write left an empty
# lease visible for an instant, so a stage (or reap / a slot count) reading the lease dir then saw nothing: this was the flaky
# "lease carries this host's name" failure in test-stage-run-hardening.sh under runner load.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SD="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-lease-atomic.XXXXXX")"
trap '[ -n "$WORK" ] && rm -rf "$WORK"' EXIT
out=$(WORK="$WORK" python3 - 2>&1 <<PY
import os, sys, threading
from pathlib import Path
sys.path.insert(0, "$SD")
import stage_run
w = Path(os.environ["WORK"]); d = w / "heavy"; d.mkdir(); f = d / "7"
stage_run.stamp(d, 7, "T7")
bad, stop = [], threading.Event()
def reader():
    while not stop.is_set():
        try: t = f.read_text().split()
        except OSError: continue
        if len(t) != 7: bad.append(t)
th = threading.Thread(target=reader); th.start()
for i in range(20000): stage_run.stamp(d, 7, "T7", i, "T%d" % i)
stop.set(); th.join()
print("BAD", len(bad), bad[:1], "TMP", len(list(w.rglob("*.tmp"))))
PY
)
if grep -q '^BAD 0 .* TMP 0$' <<<"$out"; then echo "PASS  lease rewrite is atomic (no empty or partial lease seen, no leftover temp file)"; else echo "FAIL  lease rewrite is atomic: $out"; exit 1; fi
