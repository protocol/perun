# Registers the --advise rule tests and the cost statusLine wiring test with CI (see the "Per-PR tests" step in ci.yml).
python3 scripts/test_cost_advice.py
bash scripts/test-cost-statusline.sh
