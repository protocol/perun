### Added
- agentic-delivery: `stage_run.py --run-dir DIR` refuses (exit 1) a run dir that already exists; `lkg.py verdict FILE` exits 1 with "rerun" unless the receipt is a pass for HEAD with matching runner blob (`run-ci-tests.sh` reads its own receipt back and honors `PERUN_RUN_DIR`); `wired_check.py --strict --runs FILE` (now the CI step) fails a new script with no caller or no exact-name run in the registered tests; new `vendor_drift.py TARGET` lists vendored skill files that differ from canonical (sha256) and exits 1 on drift or zero overlap (`--skills` flags deleted copies; `update-installed.sh` runs it).
- agentic-delivery: a merge train that parks a PR posts a `perun-train-refused: <head sha>` comment on it; admission skips a PR with that line for its current head, so a dropped PR is not re-ridden until a new push (invariant in `references/merge-queue-worktrees.md`).

size-budget-raise: .claude/skills/agentic-delivery/references/full-map.md 23891→24381 one routing line for the four wave-AE mechanisms
size-budget-raise: .claude/skills/INDEX.md 14569→14671 generated index row for vendor_drift.py
size-budget-raise: .claude/skills/agentic-delivery/INDEX-scripts.md 15097→15241 generated index row for vendor_drift.py
size-budget-raise: .claude/skills/agentic-delivery/references/merge-queue-worktrees.md 43476→44819 one paragraph: head-bound train refusal invariant (author filter, clear, neutralized reason)
