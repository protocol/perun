#!/bin/sh
# Needs PCSS_KEY in the environment. Judge passes repeat until every record exists (a failed call writes nothing).
cd "$(dirname "$0")" || exit 1
for a in sp v0 c1 c2 c3; do python3 -I bench.py gen tune $a; done
for a in v0 c1 c2 c3; do for i in 1 2 3; do python3 -I bench.py judge tune $a sp; done; python3 -I bench.py score tune $a sp; done
python3 -I bench.py soft tune v0 c1 c2 c3
# held-out: only the arm named in the ledger `selected` line
for a in sp v0 c1; do python3 -I bench.py gen held $a; done
for a in v0 c1; do for i in 1 2 3; do python3 -I bench.py judge held $a sp; done; python3 -I bench.py score held $a sp; done
python3 -I bench.py paired held v0 c1
