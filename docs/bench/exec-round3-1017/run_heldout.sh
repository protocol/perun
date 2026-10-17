#!/bin/sh
# Runs the four held-out arms in parallel (needs PCSS_ENV).
cd "$(dirname "$0")" || exit 1
for s in idea-critic agentic-ceo; do for a in PERUN_r3a PERUN_v0; do JOBS=4 python3 -I bench3.py run $s $a h3 > run-$s-$a.log 2>&1 & done; done
wait
