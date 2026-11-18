# review_checks.sh with no timeout(1) or gtimeout on PATH: the perl timebox stops a SIGALRM-ignoring gh, and the slither solc probe still runs.
bash scripts/test-review-checks-hub-no-timeout.sh
