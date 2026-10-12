# Operating discipline — the always-on layer, one entry point

Read this when: setting up a new machine or a new fleet, or auditing whether the always-on
operating layer (not just the review method) actually installed. Each item below is one line —
a pointer to the section that owns the depth, never a restatement (this file's own row in
`scripts/size-budgets.tsv` keeps it that way; a size-budget failure on this file is itself the
drift signal). Install + verify: **Install and self-check** below.

1. **Communication + minimal-code modes, main session and every subagent** — `host-enforcement.md` **Standing modes at SubagentStart**; `multi-session-coordination.md` **A standing house default must live where every subagent reads it**.
2. **Hand-back caps, two-tier** — `host-enforcement.md` **Subagent handback: fields-only, mechanically capped**.
3. **Model and effort routing** — `deep-code-review`'s `model-tiering.md` **Route delivery lanes by work type and stage** (path-based review strictness stays `templates/review-tiers.tsv`); the host-enforced subagent model pin: `host-enforcement.md` **Subagent model + cache-TTL pin**.
4. **Fan-out probing** — `fanout-host-sizing.md` **Gate on free RAM and the swap trend** (`scripts/host_probe.py`).
5. **Usage-window pacing** — `cost-quality-guardrails.md` §2 **Lane caps** (`scripts/token_report.py --budget`, `agentic-ceo` sibling skill).
6. **Conductor rules** — single merger / back-to-back draining: `merge-queue-worktrees.md` **Parallelizing the merge *seat* backfires**; union-proven train: `gate-epistemology.md` principle 6 (`scripts/merge_train.py`); close an issue only on a confirmed merge: `unattended-trackers.md` **An open tracker issue is not proof the fix is absent**; verify a lane's claim against gate evidence, never its self-report: `gate-epistemology.md`; decorrelated security review: `roles.md` **Independence where it counts**; never report a target state as achieved without evidence: `project-state.md` **Record contract**.
7. **Cross-session coordination** — one writer per file, a durable claim token: `multi-session-coordination.md` **An announcement comment is not an atomic claim**; the conductor's go before a heavy spawn: `fanout-host-sizing.md` **Environment probe procedure**; no permission laundering: `multi-session-coordination.md` **A persistent cross-peer permission asymmetry**.
9. **Resource policy** — read `.perun/policy.json` before choosing parallelism, CI, or model; default is efficient on every dimension, push harder only where named: `docs/for-fleets.md` **Efficiency by default** (`scripts/perun_policy.py get <dim>`).
8. **Safety rules** — never run a delete or kill experiment on a host (use a container/VM, or skip it) and never `rm -rf` a variable-built path (an empty `$W` turns `rm -rf "$W"/*` into `rm -rf /*`); deny rules match command text only (`/bin/rm`, `bash -c` bypass them), so the OS sandbox (`sandbox.enabled`, `allowUnsandboxedCommands: false`, set by `install.sh --apply-operating-layer`, opt out `--no-sandbox`; `operating_selfcheck.py` reports it off as `MISSING RED`) is the real boundary; no kill by pattern / never stop a shared server: `dev-env-ownership.md` **Local environment — the five-step stack procedure**; no hook bypass: `red-gate-triage.md` **A landed flaky-test fix only protects a branch that already has it** (`--no-verify` never silent); no bare `git stash` across lanes: `worktree-isolation.md` **A worktree does not isolate repo-global refs**; privacy gates: `deep-code-review`'s `privacy-by-design.md`.
9. **Spend attribution** — name every API key or vendor workspace `<tracker-project-id>-<handle>` (the handle is the text after the last hyphen), and prefer one key per project over a shared OAuth login, which cannot be split afterwards. Set attribution and alerts first, hard caps last: a cap stops work, an alert only warns. `python3 scripts/spend_report.py EXPORT.csv|json [--warn AMOUNT]` groups a provider usage export by that prefix into per-project totals (offline; rows with no cost print as `UNPRICED`, never zero).
10. **Ship from a dedicated worktree** — never from the shared checkout (a stale or dirty tree ships the wrong commit). A browser smoke under the sandbox needs an exact-prefix `sandbox.excludedCommands` rule (e.g. `"npx playwright test"`); write the command with no output redirects (`>`, `2>&1`, `| tee`) so the pattern still matches, and have the test write its own report file instead.

## Install and self-check

`install.sh --with-operating-layer` writes `settings.operating-layer.json.new` next to the
target's own `.claude/settings.json` (never overwrites it) — the `SubagentStart` house-default
injector (`scripts/subagent_start_inject.py`), both `SubagentStop` hand-back-cap tiers
(`scripts/handback_cap.py`, default + one `matcher`-scoped read-only tier), and the
`CLAUDE_CODE_SUBAGENT_MODEL` pin, every path relative to the installed skill — and prints how to
merge the snippet into the real settings file.

`install.sh --with-delivery --apply-operating-layer TARGET` applies it instead: it jq-merges the
template's hooks and env (plus `model: sonnet` when unset; existing env and model win) into
`TARGET/.claude/settings.local.json`, appends only hook entries not already present (re-running
yields an identical file), writes `settings.local.json.bak` first when the file changes, writes
`.claude/agents/delivery-lane.md` (Sonnet, terse, one-line hand-back) only if absent, and fails
closed when `jq` is missing. Every install records its flags in `TARGET/.claude/.dcr-install-flags`;
`scripts/update-installed.sh TARGET...` replays them from this checkout so installed skills pull the
latest main (update this checkout first). The applied layer also wires `scripts/perun_auto_update.py`
on SessionStart and UserPromptSubmit: at most every 6h, detached, it replays the same flags from the
newest release tag, skipping (and logging why) on a merge/train lock or an edited managed file; policy
`auto_update: off` or `install.sh --no-auto-update` disables it. Skills and settings live-reload, so no
session restart is needed.

`scripts/operating_selfcheck.py [--settings F] [--skill-root D]` reports, per item above,
`PRESENT`, `MISSING`, or `COULD_NOT_CHECK <why>` — the three settings-backed items (1's injector,
2's two-tier cap, 3's model pin) read `--settings`; the two script-file items (4, 5) check the
installed skill tree; items 3's routing doctrine, 6, 7, and 8 are protocol-only (no host artifact
represents prose) and always report `COULD_NOT_CHECK: protocol only`. `--selftest` proves every
branch with throwaway settings files, before and after a merge.

Copy-paste `/loop` prompts and scheduled-task templates for the coordinator, peer and cleanup loops live in
`templates/loops/` (installed with `--with-delivery`); event-driven or every 20 minutes at the fastest.
