# Bench-integrity gate (checks documented in scripts/bench_check.py): tests, then only bench dirs new vs origin/main (missing origin/main is an error).
python3 scripts/test_bench_check.py
python3 scripts/bench_check.py --changed origin/main
