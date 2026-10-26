# Operating discipline — the always-on layer, one entry point

Read this when: setting up a new machine or a new fleet, or auditing whether the always-on
operating layer actually installed. Each item below is one line —
a pointer to the section that owns the depth, never a restatement (this file's own row in
`scripts/size-budgets.tsv` keeps it that way; a size-budget failure on this file is itself the
drift signal). Install + verify: **Install and self-check** below.

**Drive to the goal (first rule).** A task ends only when the requested outcome is met and verified. Waiting on a job, gate, budget or answer means you start the next independent item. When everything is blocked, create the next lever: measure, research, ask peers, build the zero-cost part. The only stops are "goal met with evidence" or "every path needs the owner", handed back as one batched question.

Two spend modes. Cautious by default; at maximum pace, once the owner grants it, caps, waits and approval pauses lift and spend rises only where it buys speed or quality, behind a waste filter. The rule, its triggers, the push grant and the `perun_policy.py` knobs live once, in `templates/lane-preamble.md` **Drive to the goal**.

1. **Communication + minimal-code modes, main session and every subagent** — `host-enforcement.md` **Standing modes at SubagentStart**; `multi-session-coordination.md` **A standing house default must live where every subagent reads it**.
2. **Hand-back cap** — `host-enforcement.md` **Subagent handback: fields-only, mechanically capped**.
3. **Model and effort routing** — `deep-code-review`'s `model-tiering.md` **Route delivery lanes by work type and stage** (path-based review strictness stays `templates/review-tiers.tsv`); the host-enforced subagent model pin: `host-enforcement.md` **Subagent model + cache-TTL pin**.
4. **Fan-out probing** — `fanout-host-sizing.md` **Gate on free RAM and the swap trend** (`scripts/host_probe.py`).
5. **Usage-window pacing** — `cost-quality-guardrails.md` §2 **Lane caps** (`scripts/token_report.py --budget`, `agentic-ceo` sibling skill).
6. **Conductor rules** — single merger / back-to-back draining: `merge-queue-worktrees.md` **Parallelizing the merge *seat* backfires**; union-proven train: `gate-epistemology.md` principle 6 (`scripts/merge_train.py`); close an issue only on a confirmed merge: `unattended-trackers.md` **An open tracker issue is not proof the fix is absent**; verify a lane's claim against gate evidence, never its self-report: `gate-epistemology.md`; decorrelated security review: `roles.md` **Independence where it counts**; never report a target state as achieved without evidence: `project-state.md` **Record contract**.
7. **Cross-session coordination** — one writer per file, a durable claim token: `multi-session-coordination.md` **An announcement comment is not an atomic claim**; the conductor's go before a heavy spawn: `fanout-host-sizing.md` **Environment probe procedure**; no permission laundering: `multi-session-coordination.md` **A persistent cross-peer permission asymmetry**.
9. **Resource policy** — read `.perun/policy.json` before choosing parallelism, CI, or model; default is efficient on every dimension, push harder only where named: `docs/for-fleets.md` **Efficiency by default** (`scripts/perun_policy.py get <dim>`). `ci: local-first|cloud|auto` (`perun_policy.py ci`) says where the gates run: on `local-first` run every gate locally and push each PR once.
8. **Safety rules** — never run a delete or kill experiment on a host (use a container/VM, or skip it) and never `rm -rf` a variable-built path (an empty `$W` turns `rm -rf "$W"/*` into `rm -rf /*`); deny rules match command text only (`/bin/rm`, `bash -c` bypass them), so `destructive_guard.py` (PreToolUse, wired by the operating layer) also denies the wrapped forms and `git reset --hard`, `git clean -f`, `find -delete`, `dd`/`mkfs`, `curl|sh` and kill-by-pattern as a best-effort string-level check (no allow list; the owner runs a wanted command with `!`); the OS sandbox (`sandbox.enabled`, `allowUnsandboxedCommands: false`, set by `install.sh --apply-operating-layer`, opt out `--no-sandbox`; `operating_selfcheck.py` reports it off as `MISSING RED`) is the real boundary; no kill by pattern / never stop a shared server: `dev-env-ownership.md` **Local environment — the five-step stack procedure**; no hook bypass: `red-gate-triage.md` **A landed flaky-test fix only protects a branch that already has it**; no bare `git stash` across lanes: `worktree-isolation.md` **A worktree does not isolate repo-global refs**; privacy gates: `deep-code-review`'s `privacy-by-design.md`.
9. **Spend attribution** — name every API key or vendor workspace `<tracker-project-id>-<handle>` (the handle is the text after the last hyphen), and prefer one key per project over a shared OAuth login. Set attribution and alerts first, hard caps last: a cap stops work, an alert only warns. `python3 scripts/spend_report.py EXPORT.csv|json [--warn AMOUNT]` groups a provider usage export by that prefix into per-project totals (offline; rows with no cost print as `UNPRICED`, never zero).
10. **Ship from a dedicated worktree** — never from the shared checkout (a stale or dirty tree ships the wrong commit). A browser smoke under the sandbox needs an exact-prefix `sandbox.excludedCommands` rule (e.g. `"npx playwright test"`); use no output redirects (`>`, `2>&1`, `| tee`) so it still matches, and let the test write its own report.
11. **Teardown and cleanup** — stop what you started, leave nothing running. (a) Before hand-back, stop your own PIDs and run `ROOT=<worktree> scripts/reap_own.sh --report`: it lists listeners and orphans (ppid 1: not seen under a Linux subreaper) whose cwd or command line is under the worktree, `orphans=0` is the pass, `COULD_NOT_CHECK` is not, and the hand-back quotes the line (the Lane teardown line of `templates/lane-preamble.md`). (b) A script that starts a server, browser or loop stops it in an EXIT trap and bounds every endless loop with a counter or deadline (`scripts/teardown_lint.py`, a per-file heuristic with documented limits). (c) One queued heavy job per worktree, and trains and prechecks take slots before lane jobs: the train side is `heavy_gate.py`'s exclusive lease; the per-worktree limit is a lane rule, no check. (d) Claim atomically before any lookup (`scripts/_lock.sh` `lock_take`, an `mkdir`); a per-run log path is a lane rule, no check. (e) Delivered worktrees are removed after landing and dirty ones archived first (`scripts/clean_finished.sh`). (f) Tests drop runner switches by prefix before each test: `scripts/scrub_env.sh` does it for `SCRUB_PREFIXES` a caller sets, but nothing sets it yet, so this is a lane rule until a caller does. Test: `scripts/test-teardown.sh`.

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
`.claude/agents/delivery-lane.md` only if absent, and fails
closed when `jq` is missing. Every install records its pack flags in `TARGET/.claude/.dcr-install-flags` and the capability-adding ones (`--apply-operating-layer`, `--with-operating-layer`, `--no-sandbox`) in the untracked `.dcr-install-flags.local`;
`scripts/update-installed.sh TARGET...` replays them from this checkout so installed skills pull the
latest main. The applied layer also wires `scripts/perun_auto_update.py`
on SessionStart and UserPromptSubmit: at most every 6h, detached, it replays the same flags from the
newest release tag, skipping on a merge/train lock or an edited managed file; policy
`auto_update: off` or `install.sh --no-auto-update` disables it. Auto-compact plus re-inject replaces "restart the session" (a session cannot `/clear` itself): the layer sets
`autoCompactWindow: 200000` only when no user, project or local settings file sets it (policy `auto_compact: off` skips it), and a SessionStart hook
(`compact|startup|clear`, `scripts/handoff_inject.py`) re-injects the newest `.claude/handoff*.md`, 2KB max. Agents write that handoff
before any reset and never tell the owner to restart. Two advisory cost hooks ride along: `scripts/context_nudge.py` (UserPromptSubmit) prints at most two lines:
past 250k tokens (`PERUN_CONTEXT_NUDGE_TOKENS`, again per 50k of growth) the handoff nudge plus the host's session commands (host from env or `PERUN_HOST`), and a model/effort hint on a work-kind change; `scripts/lane_resume_nudge.py` (PreToolUse `Agent|Task`)
advises resuming an earlier same-domain lane with SendMessage instead of paying a new lane's startup re-read (the lane's tool-call cap does not reset on resume: a fresh lane is better for a large remainder). Neither
blocks; both fail open. The layer also wires `scripts/lane_cap.py` (PostToolUse) with `LANE_TOOL_CAP=250`:
a lane is told to checkpoint at 80% and stop at the cap; `LANE_TOOL_CAP_<TYPE>` overrides per lane type. `scripts/ceo_altitude_guard.py` (PreToolUse + UserPromptSubmit) is inert until policy `role` is `ceo` (warn) or `ceo-strict` (block): it flags the main session's hand edits of source and tests, never a lane's; the owner lifts it per turn with `ceo:off`; `operating_selfcheck.py` prints those edits per session, counted even while `role` is `off`.

`scripts/operating_selfcheck.py [--settings F] [--skill-root D]` reports, per item above,
`PRESENT`, `MISSING`, or `COULD_NOT_CHECK <why>` — the three settings-backed items (1, 2, 3's pin) read `--settings`; the two script-file items (4, 5) check the
installed skill tree; items 3's routing doctrine, 6, 7, and 8 are protocol-only and always report `COULD_NOT_CHECK: protocol only`. `--selftest` proves every branch.

Copy-paste `/loop` prompts for the coordinator, peer and cleanup loops live in
`templates/loops/` (installed with `--with-delivery`); event-driven or every 20 minutes at the fastest.
