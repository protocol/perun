### Fixed
- `pre-push-verify.sh` now stops with one line (`git fetch <remote> <branch>`) when a new branch is pushed, the remote has its default branch, and the local copy of that branch is missing, instead of verifying the branch's whole history, which once took 30 minutes. An empty remote, or one without that branch, still gets the full-history check.
