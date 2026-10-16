# Perun for agent fleets

**If you run several agents in parallel, install the delivery overlay and wire
the gates: `./install.sh --full --with-gates /path/to/project`, plus
`--with-ceo` for the owner task ledger.** Each rule below is a script with an
exit code, so a lane that breaks it is stopped rather than reminded. Every
script below runs its own self-test (`--selftest`) in this repository's CI.
What Perun is: [the README](../README.md). Basic install:
[`getting-started.md`](getting-started.md).

## What `--with-gates` writes

| File | What it does |
|---|---|
| `.github/workflows/dcr-gates.yml` | Runs the gates on push and PR. Edit the trigger branch if your default branch isn't `main`. |
| `scripts/dcr-gates.sh` | Calls the gate scripts inside the installed skills; holds no copy of their logic, so re-running `install.sh` upgrades the checks. |
| `.githooks/pre-push` | Reruns your fast lint + unit tier (`DCR_PREPUSH_CMD`) before each push. Off until you run `git config core.hooksPath .githooks`. |

Separately opt-in, never written by `install.sh`: copy
`.claude/skills/deep-code-review/templates/perun-review.yml` to
`.github/workflows/` for PR-native review. A read-only job runs the review and
a second job (no PR checkout, no model key) posts one pending review, one
sticky comment and one check run with severity counts, replacing its prior
pending review on each push. Prerequisites: the `ANTHROPIC_API_KEY` secret, a non-empty `.banlist.txt`
(`post_review.sh` fails closed without it) and a pinned `CLAUDE_CODE_VERSION`. The file header documents the spend cap and fork
hardening.

It never overwrites an existing file at these paths; it writes `<path>.new`
instead. Always on: `fix_class_gate.py` (every `fix:` commit touches a pinned
test or carries a `No-Test-Reason:` trailer) and `binaries_gate.py` (no
committed screenshots, archives, or build output). The `DCR_*` flags below are
opt-in and off by default; the header of `scripts/dcr-gates.sh` documents each
flag's inputs (for example, `DCR_FOCUS_GATE` needs `DCR_OWNER_EMAIL` from
protected CI config). A flag set without its skill installed fails, never
skips.

## Mechanisms

| Need | Script | Blocks or reports | Switch on |
|---|---|---|---|
| Short subagent handbacks | `agentic-delivery/scripts/handback_cap.py` | A subagent's final chat message over 800 characters or 10 lines (defaults; `HANDBACK_MAX_CHARS`, `HANDBACK_MAX_LINES`); fenced code blocks and `! ` command lines are not counted, but the whole message may not pass 5 times the character cap. With `HANDBACK_REQUIRE_STATUS=1`, also a handback with no status line (`verified`, `unverified`, or `done | evidence | next`). The subagent is sent back to fix it, not killed. | `SubagentStop` hook in `.claude/settings.json`; `install.sh --with-gates` prints the snippet. |
| Lane tool-call cap | `agentic-delivery/scripts/lane_cap.py` | Never blocks. Counts a subagent lane's tool calls (never the main thread); at 80% of the cap it tells the lane to checkpoint an `UNVERIFIED` handback, at the cap to stop and hand back. | `PostToolUse` hook with `LANE_TOOL_CAP=<n>` or `LANE_TOOL_CAP_<TYPE>=<n>` |
| Main session stays CEO | `agentic-delivery/scripts/ceo_altitude_guard.py` | Counts the main session's direct source edits per session (always; `operating_selfcheck.py` prints them). With policy `role=ceo` it warns on the 2nd direct source edit and the 4th build/test run in a turn (`delegate: spawn a lane with the brief ...`); with `role=ceo-strict` it blocks them. Never touches a subagent. Docs, config, memory, handoff, changelog and temp-dir files are never flagged. `ceo:off` in an owner prompt lifts it for that turn. | `PreToolUse` + `UserPromptSubmit` hooks (operating layer), armed by `perun_policy.py set role ceo`. |
| Strong model and independent review on critical paths | `agentic-delivery/scripts/tier_gate.py` | A commit touching a tier-1 path (`templates/review-tiers.tsv`) without `Model: opus` and an independent `Reviewed-By: <id> receipt:<ref>` trailer whose receipt exists; a tier-2 commit without the reviewer trailer. `--github <PR>` instead requires an APPROVED review from another login. One shared account cannot prove independence; use a separate reviewer account. | Run `tier_gate.py <base>..<head>` (or `--github <PR>`) as a required check |
| Cost cuts that let a defect escape | `agentic-delivery/scripts/escaped_defects.py` | An escaped Blocker (`Regression-Of:` fix) traced to a `Cost-Cut:` commit (revert it), two cuts in one window, or a cut inside the 4-week baseline. | Run per measurement window |
| Stay on the owner's priority | `agentic-delivery/scripts/focus_gate.py` | Work outside an owner-committed `.claude/PRIORITY.md` until its acceptance command passes on a clean checkout, or the priority is blocked on another party with evidence. Agent-written or over-broad records are rejected. | `DCR_FOCUS_GATE=1` |
| No cosmetic work over an aged P0 | `agentic-delivery/scripts/priority_gate.py` | A presentation-only PR while an aged priority issue has no PR citing it. | `DCR_PRIORITY_GATE=1` |
| One ranked queue when P0 is inflated | `agentic-delivery/scripts/queue_guard.py` | Prints the next issue to pull (ranked in `PRIORITIES.md`, then oldest P0) and flags more than N unranked P0s. Read-only. | Per lane. |
| Stop re-fixing the same file | `agentic-delivery/scripts/refix_gate.py` | Re-touching a file a `fix:` commit touched in the last 72 hours (default) without a test or eval change or a `Refix-Reason:` trailer. | `DCR_REFIX_GATE=1` |
| Closing keywords stay in scope | `deep-code-review/scripts/closes_lint.py` | A `closes #N` for an issue or PR the change doesn't own. | `DCR_CLOSES_LINT=1` |
| Keep every owner ask | `agentic-ceo/scripts/task_ledger.py` | One `.claude/TASKS.md` per project: asks verbatim, `done` needs evidence (sha, URL, `#N`, or test id), `next` returns one item, `reconcile` finds asks lost to compaction. | Run by the conductor (`--with-ceo`). |
| One requirement list across sources | `agentic-delivery/scripts/feedback_ledger.py` | Merges feedback exports, doc comments, transcripts, and design exports; turns each disagreement into an owner question; never decides. | Run on demand. |
| Isolated lanes | `agentic-delivery/scripts/lane_guard.py` | A write-lane not in its own linked worktree on its expected branch, or sharing it with another live process. | First step of every write-lane. |
| No double-claimed work | `agentic-delivery/scripts/claim_probe.py` | Starting an item that overlaps an open PR, branch, or live claim; crossed claims resolve to the earliest. | Before each claim. |
| Coordination board | `agentic-delivery/scripts/board_post.py`, `board_sync.py`, `board_state.py` | Typed, capped, privacy-linted posts on one issue; read from a per-agent cursor; render current state into the issue body. | Per the delivery skill. |
| Parallel test runs | `agentic-delivery/scripts/serial_gate.py` | Path-scoped test selection that falls back to the full suite when unsure, plus a kernel lock for shared-state steps. | Per lane. |
| Is a quiet lane alive? | `agentic-delivery/scripts/lane_liveness.py` | Reports liveness from positive evidence; never issues a kill verdict. | On demand. |
| Returning reviewer | `agentic-delivery/scripts/review_digest.py` | A change digest since the last review, instead of a full re-read. | On demand. |
| "Deployed" means deployed | `agentic-delivery/scripts/surface_check.py` | A done/deployed claim whose running build id doesn't match the sha; a failed check is `COULD_NOT_CHECK`, never a pass. | Before claiming done. |

Paths are relative to `.claude/skills/` in the installed project. Each script
documents itself in its header and prints usage with `--help`.

## Keep token cost down

- Brief lanes to a one-line handback (`status | evidence | next`) with the
  deliverable in a file; the cap above is the backstop.
- Apply the Claude Code settings that cut per-turn tokens (Bash output cap,
  skill-listing budget, subagent prompt cache), documented with starting values
  in [`host-enforcement.md`](../.claude/skills/agentic-delivery/references/host-enforcement.md).
- Load only the skills a lane needs. Each skill's `SKILL.md` routes to its
  references on explicit triggers, so a lane that doesn't hit a trigger never
  reads that depth.

## Efficiency by default

Every resource is spent efficiently unless you name a front to push. One file,
`.perun/policy.json`, sets a mode per dimension: `efficient` (default), `maximize`,
`off`, or a numeric cap. Dimensions: `tokens`, `local_cpu`, `local_ram`,
`github_actions`, `paid_api_calls`, `network`. Example, push local CPU, stay off GitHub runners:

```json
{ "local_cpu": "maximize", "github_actions": "off", "share_learnings": "auto" }
```

- `local_cpu: maximize` fills idle cores, never past the load, free-RAM and swap
  ceilings in `host_probe.py`. `train_land.sh` exports `PERUN_JOBS` from it.
- `github_actions: off` means local gates only: Perun's merges carry `[skip ci]`,
  it never polls or re-runs CI, and the shipped workflows skip when the repository
  variable `PERUN_GITHUB_ACTIONS` is `off`. Lanes also end every pushed branch commit
  with `[skip ci]` (a lane rule in the preamble, not enforced by code; `perun_policy.py skip-ci` prints the token), so opening a PR or
  pushing a branch starts no runner either. Limitation: a required status check never reports on a
  `[skip ci]` commit, so branch protection that requires checks blocks the merge; satisfy them with
  local gates (or an owner-approved admin merge). Perun's own scripts create no pushed commits.
- Set it without hand-writing JSON: `perun_policy.py set local_cpu maximize`, or at install
  `./install.sh --policy local_cpu=maximize,github_actions=off,share_learnings=auto`.
- `tokens`: enforced only as a lane cap. `perun_policy.py lanes` and `heavy-slots` (and host_probe's lane cap)
  cap at 2 for `efficient`, 1 for `off`, N for a number (never a token budget); `maximize` lifts the cap.
  Cheapest fitting model tier, no duplicate review passes and terse hand-backs are lane guidance, not enforced.
- `share_learnings` (`auto|ask|off`, default `ask`) governs `share_learning.py`; `auto` also runs it at the end of `/perun-run`, after its privacy gate.
- `role` (`off|ceo|ceo-strict`, default `off`) is not a resource: it arms `ceo_altitude_guard.py` for the main session. Set it with `perun_policy.py set role ceo` or `--policy role=ceo`; env `PERUN_ROLE` overrides it per process (`PERUN_ROLE=off` for a top-level lane or peer session, which has no `agent_id` to tell it from a main session).
- Agents read the policy (`python3 scripts/perun_policy.py get <dim>`) before choosing
  parallelism, CI, or model. A malformed file fails closed.

Self-improvement loop: a field lesson is generalized and privacy-checked, filed as an
upstream issue (deduped, logged to a local ledger), fixed in a release, then measured
against the benchmark corpus before the next lesson is trusted.

## Where the doctrine lives

- Parallel sessions, claims, and the board:
  [`multi-session-coordination.md`](../.claude/skills/agentic-delivery/references/multi-session-coordination.md)
- Running without an owner present:
  [`unattended-operating-mode.md`](../.claude/skills/agentic-delivery/references/unattended-operating-mode.md)
- Proving a handback's claims:
  [`verification-handback.md`](../.claude/skills/agentic-delivery/references/verification-handback.md)
- Lane speed and handback size:
  [`fast-agentic-delivery.md`](../.claude/skills/agentic-delivery/references/fast-agentic-delivery.md)
