# Standing check (#1592): every guard/hook script records an owner, a reason and a review date. Offline.
bash scripts/test-rails.sh
bash scripts/ci-gates.sh rails .
