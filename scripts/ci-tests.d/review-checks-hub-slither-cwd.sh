# review_checks.sh runs slither from the temp dir, never the repo, so a committed foundry.toml cannot pick the solc binary it runs; stub slither, plus a live probe when slither is installed.
bash scripts/test-review-checks-hub-slither-cwd.sh
