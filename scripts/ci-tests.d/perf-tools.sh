# Registers the perf tools: perf_compare.sh (hyperfine A/B), app_pentest.sh --load (k6 smoke), and the heavy_gate.py hold on perf_compare.sh.
bash scripts/test-perf-compare.sh
bash scripts/test-app-pentest-load.sh
python3 scripts/test_heavy_gate_perf.py
