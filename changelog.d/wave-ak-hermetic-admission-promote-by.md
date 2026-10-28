### Added
- agentic-delivery: `scrub_env.sh CMD` now also gives the child an invalid `GH_TOKEN`/`GITHUB_TOKEN`, an empty throwaway `GH_CONFIG_DIR` and a refusing proxy with loopback direct, no ssh agent, no global git config or credential helper (`PERUN_ALLOW_NET=1` drops only the proxy, logged), so a test cannot post to a real PR even when it calls `gh` by absolute path past a PATH stub; `run-ci-tests.sh` runs every ci-test through it and drops `CLAUDE*` session vars.
- agentic-delivery: `bg_admit.py admit SCRIPT` admits a background or shadow job only if it declares `# disk-cap:`, a `trap ... EXIT` cleanup and a `# disk-stop:` rule backed by a df/disk_usage check (`job_lease.py run --admit -- CMD` admits the script CMD actually runs); `bg_admit.py untrapped` lints shell scripts that call mktemp with no trap against the shrink-only `scripts/mktemp-trap-baseline.tsv`.
- Promote-by ratchet: `scripts/promote-by.tsv` lists a promote-by date for every shadow-default policy flag (`train_gate`, `lkg_gate`); `scripts/test_promote_by.py` fails when one is overdue or more than 120 days out (keeping a flag in shadow means recording a decision and moving the date).

size-budget-raise: .claude/skills/INDEX.md 14671→14767 generated index row for bg_admit.py
size-budget-raise: .claude/skills/agentic-delivery/INDEX-scripts.md 15241→15388 generated index row for bg_admit.py
