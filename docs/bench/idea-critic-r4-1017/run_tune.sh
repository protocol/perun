#!/bin/sh
# Tune split: rival frozen first, then the four arms in parallel (needs PCSS_ENV).
cd "$(dirname "$0")" || exit 1
python3 -I bench4.py rival tune > run-rival-tune.log 2>&1 || exit 1
for a in v0 cA cB cC; do JOBS=3 python3 -I bench4.py run PERUN_$a tune > run-tune-$a.log 2>&1 & done
wait
