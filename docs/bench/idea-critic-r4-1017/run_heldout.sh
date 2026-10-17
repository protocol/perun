#!/bin/sh
# Held-out split: scenarios, then the rival once, then the two arms in parallel (needs PCSS_ENV and network to llm.hpc.psnc.pl).
cd "$(dirname "$0")" || exit 1
python3 -I bench4.py scen > run-scen.log 2>&1 || exit 1
sha256sum scenarios4/idea-critic-h4.json > SHA256-scenarios4.txt
python3 -I bench4.py rival h4 > run-rival-h4.log 2>&1 || exit 1
for a in cA v0; do JOBS=4 python3 -I bench4.py run PERUN_$a h4 > run-h4-$a.log 2>&1 & done
wait
