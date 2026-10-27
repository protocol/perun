# Host capability & enforcement contract

**Read this when** claiming that state, permissions, or spend are *enforced*
rather than merely followed, briefing a worktree-isolated write-lane, or
designing a host adapter for this overlay.
A claim-honesty framework plus an optional interface: **no sandbox, budget
service, or durable runtime ships here** (only the two scripts named below). It
applies `SKILL.md` principle 3 (a check that could not run is `UNVERIFIED`,
never a pass) to the coordination layer itself.

## Claim only the level you observed

Three levels, and a markdown instruction or an unused example hook never reaches
the third:

| Level | What supports the claim | What it cannot establish |
|---|---|---|
| **Protocol** | The agent follows the skill and records its decisions/receipts | Cannot itself prevent bypass, lost state, a forbidden action, or overspend |
| **Validated artifact** | A named validator checks a specific schema/invariant against a pinned artifact, and its actual result is recorded | Shape validity is not receipt truth, live behaviour, or action authorization |
| **Host-enforced** | A tested adapter intercepts the real action boundary and denies disallowed actions using policy/state the worker cannot edit | Covers only the tested events/actions/host versions; other paths stay protocol-only |

Declare capability **per control** (state, permission, spend, isolation, model
choice, tool/capability access, receipt capture), not once for a whole host. Record host + version, the
date observed, the level, the probe evidence, and the paths still unsupported. A
skill directory, a model name, a worktree, or a hook *example* is not evidence of
enforcement. Probe the actual tool/auth/model-control availability; label
inherited or unavailable controls as such, and **fail or narrow the dependent
action when a required control is absent** — never convert an unavailable check
into a pass or into authority.

A prompt-level "do not use tool X" is a **protocol** control only — instructions are not a sandbox.
The **host-enforced** form spawns the worker with an allowed-tools set that excludes X (or denies it
at the execution boundary); the protocol fallback audits the receipt's tool calls afterward. Declare
tool access at the level you can enforce; narrow the dependent action when only the prompt exists.

**The mirror mismatch: a brief telling a no-write agent type to write.** The tool-omission control above cuts
both ways — a type spawned with no write tool cannot honor a brief line like "write findings to `<path>`," so
the dispatch fails silently: the agent still runs, its findings land only in its own transcript, and its
handback has no artifact to cite, so the orchestrator can only mark it `UNVERIFIED`. One observed run: 3 of 3
handbacks from a read-only type briefed to write a file came back `UNVERIFIED` this way. **Rule: a brief for a
no-write/read-only type asks for findings inline in the handback, never a path to write.** **Check:** lint the
drafted brief for the type's declared capability — a "write to `<path>`" (or equivalent write-instruction)
phrase paired with a read-only/no-write agent type fails the brief before dispatch, the same pre-flight-the-gate
discipline `unattended-trackers.md`'s marker-shape check applies to a different mismatch.

## Isolated write-lanes: guard first, stop at the first refusal

Isolation is a control too: a lane that lost it writes a shared tree. A write-lane brief's first
command is `git rev-parse HEAD && python3 .claude/skills/agentic-delivery/scripts/lane_guard.py
--expect-branch <branch>` — the direct read probes any command-wrapping hook; `lane_guard.py`
(`--selftest`) requires `--expect-branch` (`--allow-any-branch` waives it, never in a lane brief),
prints one quotable `LANE_GUARD REFUSE:` line and exits non-zero unless the cwd is a linked worktree
on exactly that branch and it is not a default one (origin/HEAD's target, `main`, `master`, or the
main checkout's branch). At that refusal, or any later git or file-write refusal, the lane stops and
hands back the line plus its changed files; any other missing control narrows only the dependent
action (above). The brief names the dodges as out of bounds, own branch
included: an absolute binary path, a wrapper (`env`, `sh -c`, a script), a subshell — all
permission-laundering (`multi-session-coordination.md`). The orchestrator audits live processes
(`pgrep -fl 'git push'`), not only lane reports. Without host isolation, the orchestrator makes each
worktree (`git worktree add`) and spawns the lane there, confined by the brief; blocked work is
re-shipped by a fresh lane in a fresh worktree, never salvaged via git in the blocked tree. Each
receipt records its isolation mode (host / orchestrator-worktree).

## Optional adapter interface (proposed, not shipped)

If a host exposes the events, an adapter normalizes only those it actually has;
missing events stay explicit gaps.

| Event | Required adapter behaviour |
|---|---|
| Session start / resume / checkpoint | Load and write the project record (`project-state.md`); reconcile live owners and unknown effects before admitting any retry |
| Task dispatch / completion | Bind owner, scope, dependencies, and budget; capture the real tool/artifact receipt separately from the worker's own summary |
| Before a paid or consequential action | Check current authority, required evidence, state revision, and the resource bound; reserve capacity atomically before admitting the action |
| Result / failure / cancellation | Observe the actual result and usage; reconcile the reservation; record pending/unknown effects; keep failed-attempt costs |
| Objective / permission change | Invalidate affected queued work and stale grants; cancel where supported and reconcile in-flight effects |

Reservations must cover outstanding work **plus** the next permitted call
(tool/provider charges included); deny admission if the bound cannot hold. An
estimate with no bounded call or stop mechanism is not a hard cap. A cancellation
*request* is not proof of cancellation — hold the reservation for unknown or
in-flight charges until the status is observed, and record overshoot honestly.
Replay must deduplicate by event identity while re-checking permission afresh: a
duplicate receipt must never bill or publish twice.

Protect policy, grants, counters, and receipt sources from the worker they
constrain; scope credentials at the real execution boundary — ordinary worktree
isolation and model instructions are **not** a security sandbox. For every
receipt, name its trust boundary (a provider/runner observation versus the
agent's own assertion).

**Before raising a claim to host-enforced,** exercise allow/deny,
malformed/stale events, replay, crash-after-effect, cancellation, revoked
authorization, and missing-hook cases, and record the observed result for that
host version and covered path. Downgrade the claim where support is missing;
never assert a cross-host conformance result you did not observe.

## Subagent handback: fields-only, mechanically capped (a Host-enforced instance)

Chat a subagent produces is billed output nobody re-reads —
`fanout-host-sizing.md`'s cost argument, made a **hook** here instead of a
prompt instruction alone (a prompt-level "keep it short" stays Protocol above,
never Host-enforced). A lane runs **tool calls only, zero prose between them**,
and its final message is **`key=value` fields only**, one per line, no
sentences: `status=VERIFIED|UNVERIFIED`, `sha=`, `result=`, `tests=`,
`blockers=`, `report=<path>`. Deliverables (code, reports, long findings) go in
files, which no hook caps; a handback names the path. **No polling.** Never
sleep/loop waiting on background work in a subagent turn — end the turn and let
the notification resume it. `subagent_start_inject.py` states the rule to every
lane at spawn; a miss of that shape is only **logged**, never sent back, because
a rewrite re-reads the lane's whole context and costs more than it saves. The
orchestrator never relays a subagent's prose; it reads the fields and the named
files.

Install: a `SubagentStop` entry running `scripts/handback_cap.py` (no `matcher`
runs on every agent; a `matcher` names the types), as in
`templates/operating-layer.settings.json`. **Use this when** a subagent's chat
handback is landing in an orchestrator's context uncapped. Stdlib-only; blocks
(exit 2, which per the host's docs continues the subagent, so no work is lost) a
handback over 800 chars / 10 lines (the 400-char fields-only target is logged
only); exempts only agent
types named in `HANDBACK_EXEMPT_TYPES` (default: 4 built-in types) — it never
inspects tools, so a custom read-only review lane is capped too; releases after
3 blocks per agent. Knobs: its header. The `VERIFIED`/`UNVERIFIED`
status check and `lane_cap.py` tool-call cap: `cost-quality-guardrails.md` §2.

**Lane audit.** When a stop is allowed it appends one line per lane to a local
ledger (`$XDG_CACHE_HOME/perun/lane-audit.jsonl`): estimated text tokens
(narration vs handback) against tool-call tokens, counts only, read from the
lane's own `agent_transcript_path` (`transcript_path` is the parent's).
`--report` and `--scan <dir> --since-days N` print aggregates; details: the
script header.

**A harness with no report file** (a review lane's findings ARE its chat
answer) still needs a cap, never an exemption (exempt = uncapped). Matching
hooks run in parallel and any block wins, so give that type its own entry
(`matcher` = the type, env `HANDBACK_MAX_LINES=25 HANDBACK_MAX_CHARS=2000`;
add by hand), list it in
`LANE_RULES_SKIP_TYPES`, and scope the default entry's `matcher` to leave it
out: a matcher with other characters is a JavaScript regex, e.g.
`^(?!security-reviewer$).*`.

## Standing modes at SubagentStart, with per-type exemptions (a Host-enforced instance)

A standing mode that must hold for the **whole fleet** — a terse reporting voice, a
minimal-code bias, a cost rule — is enforced at `SubagentStart`, not only in agent
definitions or per-dispatch briefs (`multi-session-coordination.md` **A standing
house default must live where every subagent reads it**). `scripts/
subagent_start_inject.py` reads one project-owned `HOUSE_DEFAULTS_FILE` and injects
it via `hookSpecificOutput.additionalContext` into every newly-spawned subagent's
context, before its first prompt — the same output field the profile switch below
uses, for a different purpose (a fixed house-default file here vs. selecting between
two named profile files there); install both if a project needs both.

Exceptions are carved **mechanically, by agent type**, not left to each lane's memory:

1. **Artifacts stay normal prose** — the injected file itself says so; this hook never
   rewrites that line.
2. **A design-port/design-alignment lane is exempt from the minimal-code bias
   only, never the voice.** A line in `HOUSE_DEFAULTS_FILE` tagged `MINIMAL-CODE: `
   is dropped for any `agent_type` listed in `HOUSE_MINIMAL_CODE_EXEMPT_TYPES`
   (comma-separated; default empty) and injected with the tag stripped for every
   other type.
3. **A read-only research/review type gets a higher hand-back cap, not an
   exemption** — already the `SubagentStop` cap rule above; this hook does not
   touch the cap.

`scripts/subagent_start_inject.py` — **use this when** a house standard is drifting
because a subagent spawned without it in its brief ran verbose or wrote more than
requested. Install: a `SubagentStart` entry, as in
`templates/operating-layer.settings.json`. Stdlib-only; it always injects the fixed
`LANE_RULES` (zero prose between tool calls, a fields-only handback; skipped for
`HANDBACK_EXEMPT_TYPES` and `LANE_RULES_SKIP_TYPES`; `LANE_RULES=0` drops it) and `HOST_RULES`, plus the house
file when readable; a non-`SubagentStart` event or malformed stdin prints nothing and
exits 0 — `SubagentStart` cannot block subagent creation at all, and this hook never
tries to. The hook also appends a one-line skill-route reminder (idea-critic before an
owner ask, communication-structure before a human-facing message, agentic-ceo to choose);
`SKILL_ROUTE_REMINDER=0` drops it. `--selftest` proves the tag-strip/exempt/fail-open branches.

## Attended-to-unattended profile switch: one env var (a Host-enforced instance)

Tightening every new spawn's profile for an unattended run — one-line
handbacks, milestones-only chat, a tighter handback cap
(`cost-quality-guardrails.md` §6, `unattended-operating-mode.md` **The default
autonomous-run profile**) — should not mean hand-editing every lane's brief.
Keep the profile itself as its own house-default file (for example
`.claude/agentic-delivery-profile-unattended.md` next to an
`…-attended.md`), and select between them with **one environment variable a
`SubagentStart` hook reads** (for example `AGENTIC_DELIVERY_PROFILE=unattended`
in `settings.json`'s `env` block, or exported before the run starts) — the hook
injects the named file's contents into every newly-spawned subagent's context.
Flipping the var reaches every **new** spawn immediately; it does not retune
an already-running lane (the bridge-in-flight rider above still applies), and
it never overrides the held-lane roster / no-broadcast-to-held-lanes rule —
tightening the default profile is not authorization to message a held lane.

## Always-on host rules and the heavy-gate bypass (Claude Code)

`scripts/heavy_gate.py` (PreToolUse Bash) allows a heavy command with a WARN after 3 denies of it in the same cwd within 30 min (the lane preamble's retry-3-then-proceed); the exclusive train-lease deny is never bypassed. `scripts/session_brief.py` (SessionStart) and `scripts/subagent_start_inject.py` (SubagentStart, even without house-defaults.md) both inject the fixed `HOST_RULES` constant from `subagent_start_inject.py`, so field-logged host refusals (`sleep N` waits, `cd X &&` git chains in worktrees) are prevented at the source.

Subprocess stages are capped too: `scripts/stage_run.py -- CMD` takes the same non-exclusive heavy lease (bounded wait, then DEFER exit 75) and kills the stage's process group past `stage_timeout_min` (policy, default 120; exit 124, stage name logged). 75 and 124 are infrastructure results, never a RED: `train_land.sh` ends exit 3 "stage did not complete" without a culprit hunt and `train_flake.sh` returns 125; a command that itself exits 75/124 is reported as 1. `train_land.sh` (stages default `TRAIN_STAGE_TIMEOUT_MIN=180`, slot wait `TRAIN_SLOT_WAIT_SECS=1800`), `train_flake.sh` and `pre-push-verify.sh` run their stages through it. The lease records the stage's pid and start times, so a SIGKILLed `stage_run` has its orphaned child reaped by the next one and a reused pid never holds a slot. The `heavy_gate.py` hook waits in-hook for a transient HOLD (`PERUN_HEAVY_HOOK_WAIT_SECS`, default 60), clamped to its own timeout minus 2s; the template sets 70s and `--apply-operating-layer` replaces an old 5s entry. Before filing any issue run `scripts/file_finding.py "<title>" [keyword...]`: it searches each title word, refuses (exit 1, match printed) on an open or closed issue or a PR merged in 14 days sharing at least two title keywords, or any explicit keyword; `--force "<reason>"` overrides and logs.

Stage weights: set `PERUN_STAGE_WEIGHTS="train-browser=2,train-unit=1,lint=0.5"` (stage name = weight in slots) and `stage_run.py` records `kind@weight` on its lease, so `heavy_gate.py` and every waiting stage count it. A heavier stage waits until it fits under the slot cap (or runs alone when nothing else holds a lease, so a weight above the cap never starves); the lease is dropped when the stage ends, which frees its weight to the waiting stages on their next 1s poll. Weights are static budgets, not measured CPU: pick them once from the stage's typical core use.

`scripts/gh-shim/gh` is one PATH shim for the gh CLI: put its directory first on PATH. Idempotent reads (`pr|issue|run|release|repo|workflow` view/list, `pr checks|diff|status`, plain `gh api` GET) retry with doubling backoff (`GH_SHIM_TRIES` 4, `GH_SHIM_SLEEP` 1s) only when stderr shows a transient fault (5xx, timeout, reset, EOF, rate limit); a 404 or red checks return at once. Writes (`pr merge|create|edit|comment`, `api -X`, `-f/-F/--input`, graphql) run exactly once, because a retried write can double-post or double-merge.

## Subagent model + cache-TTL pin (a Host-enforced instance, Claude Code)

A CLAUDE.md line telling every subagent "default to the cheapest tier" is
**Protocol** only — a subagent's own `model:` frontmatter still wins over it.
On Claude Code, `CLAUDE_CODE_SUBAGENT_MODEL` (an alias or model ID) plus
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` in `settings.json`'s `env` block is
**Host-enforced** instead (the shipped template sets only the `sonnet` default and omits `FORCE`,
because `FORCE` overrides every agent's own `model:`, including the Opus high-stakes review pass) (v2.1.257+): every subagent, teammate, and workflow
agent's `model:` field (built-in Explore and Plan included) is ignored and they
run on the named model; with only `FORCE` set, on the main conversation's
model. Exceptions to declare: a fork, and a skill run in a subagent with
`model: inherit`, still run on the main conversation's model; with only
`FORCE` set, built-in Explore keeps its cap (Opus, on the Claude API).

Cache lifetime is the sibling spend control. Defaults: on a Claude subscription
within plan usage, the main conversation gets `1h` and every other request
(subagents, workflows, teammates, forks, compaction) `5m`, except a few
server-controlled helper requests (`1h`); on usage credits, an API key, or a
cloud provider, both get `5m`. Pins take `5m`/`1h` (v2.1.242+): the main
conversation's `promptCacheTtl` setting / `CLAUDE_CODE_PROMPT_CACHE_TTL` env
var, everything else's `subagentPromptCacheTtl` / `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL`.
First match wins: `FORCE_PROMPT_CACHING_5M=1` (both buckets) → the bucket's env
var → its setting → a subagent's own `experimental.cacheTtl` frontmatter
(v2.1.248+; `1h` ignored while a subscription is on usage credits) →
`ENABLE_PROMPT_CACHING_1H=1` (both buckets) → the bucket default. The
frontmatter is per-agent (Protocol); the other-requests env/setting pin or
`FORCE_PROMPT_CACHING_5M` overrides it.
Declare which control is set, and its bucket default.

Pin lane agents (anything that edits, commits, or hands back) to `sonnet`; use
`haiku` only for explicitly mechanical tasks (grep, listing, formatting).
`FORCE=1` with a haiku-class pin overrides every lane agent's own `model:`; field
result: junk commits and lost hand-backs. `perun_doctor.py` and
`operating_selfcheck.py` WARN on that combination: pin to sonnet or unset `FORCE`.

```json
{
  "env": {
    "CLAUDE_CODE_SUBAGENT_MODEL": "sonnet",
    "CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL": "1h"
  }
}
```

## Per-turn token levers (a Host-enforced instance, Claude Code)

Five `settings.json` keys cut what reaches context every turn — the host
clamps or truncates before Claude ever sees the excess, so a worker cannot
prompt its way past them (Host-enforced by the ladder above). Verified
against `settings-reference.md` / `tools-reference.md`
(`docs/standards-index.md`, 2026-09-23).

| Setting | Saves | Start at | Trade-off |
|---|---|---|---|
| `bashOutputMaxChars` | Inline chars of a *successful* Bash/PowerShell result; unset = ~30,000 inline, clamped 4,000–128,000 (v2.1.261+) | `10000` | Overflow lands in a session-dir file plus a 2,000-char preview — Claude must `Read` it back when it needs the tail |
| `skillListingMaxDescChars` | Chars of each skill's `description`+`when_to_use` resent every turn; default `1536` | `300` | A cut mid-sentence can drop the phrase that would have triggered auto-invocation of a rarely-used skill |
| `skillListingBudgetFraction` | Listing size as a fraction of the context window; default `0.01` (1%); over budget, Claude Code drops descriptions (names survive) of the least-used skills first | keep `0.01` unless 50+ skills are installed | Lower it and fewer full descriptions survive, so Claude self-selects an idle skill less often |
| `skillOverrides` | Whole skill entries — `"name-only"` drops the description, `"user-invocable-only"` hides from Claude but keeps `/name`, `"off"` hides both | `"name-only"` on every skill irrelevant to this project | Miscalled on a skill Claude actually needed, it never self-invokes; only above `"off"` does `/name` still work |
| `subagentPromptCacheTtl` | Cache write/read cost across a subagent's own turns and resumed runs (not the per-turn caps above); unset → `5m` (subagents sit outside the main-conversation bucket even on a subscription) | leave `5m` for one-shot subagents | `1h` writes at the higher cache-write rate — pays off only if that subagent is reused inside the hour, else pure loss |

`CLAUDE_CODE_SUBAGENT_MODEL` (+`_FORCE`) is the sibling model-pin lever —
see "Subagent model + cache-TTL pin" above; not restated here.

```json
{
  "bashOutputMaxChars": 10000,
  "skillListingMaxDescChars": 300,
  "skillOverrides": { "<skill-irrelevant-to-project>": "name-only" },
  "subagentPromptCacheTtl": "5m"
}
```

## Cost discipline: no push/CI spend to "see if it passes"

Run every gate locally, once, before pushing: a push, a re-run, or `gh pr
update-branch` each cost a fresh CI run for zero new signal over what the
local run already showed. "Every gate" is the quick tier; the full suite runs
once, at the blocking gate, and a second full local run pays only above the
break-even red rate `pipeline_profile.py profile` prints
(`pipeline-optimizer.md`). Mechanisms, not just prose: `ci_cost_lint.py`
(`deep-code-review/scripts/`) flags a rerun-prone workflow and `ci_cost_advisor.py`
prices it (a public repo on standard runners is free) and prints a local-first patch
(policy `ci: local-first|cloud|auto`); `token_report.py
--budget` (`agentic-ceo/scripts/`) catches a poll/re-push loop's spend;
`merge_train.py refresh` (`merge-operations.md`) defaults to printing local
merge-and-push commands per PR, never `gh pr update-branch`, unless
`--use-update-branch` opts in (its own help names the one-CI-run-per-PR
cost). `[skip ci]` is never an option on the ref main CI protects (a
required check must actually run to satisfy branch protection); prefer `gh
pr merge --auto` (merges once required checks pass, no polling) over a
watch/poll loop. The one rerun carve-out: at most one same-commit rerun, and
only when the failure log matches a known infrastructure-flake signature
(runner lost, network timeout) — `red-gate-triage.md` **A load-flaky
required gate is not a confirmed red** and `gate-epistemology.md` principle
3 own the mechanics; anything else is fixed, not rerun. None of this blocks
a genuinely new push (a real fix, a rebase after a real conflict) — only the
reflexive re-push/re-run/poll that re-buys a result a local run already
gave.

## Minimum-cost CI & token profile (universal, mandatory)

**Read this when** wiring or reviewing GitHub Actions triggers, sizing a
fleet's per-run spend, or judging whether a "required check" is actually
enforced rather than self-reported. Every control below is declared at the
level the ladder above supports — most of this section is Protocol (a repo
owner configures it; nothing here ships an enforcing adapter), and each
control says so explicitly rather than implying Host-enforced.

**Integration branches** (a `development`/staging branch that isn't the
release target): **zero GitHub-hosted CI.** Server-enforced instead of
trusted — a branch protection rule/ruleset requires PRs and restricts who can
merge/push to the integration branch to **one integrator identity**. That
identity is a **deterministic script, never an LLM session** — an LLM
holding the gate token is a prompt-injection target that can be coaxed into
minting its own green status. Run it from `launchd` (or an equivalent local
scheduler), batching the queued PRs into one merge-train gate run per cycle
and bisecting to find the culprit only when that run is red (one PR at a
time, waiting in line, is the failure mode this avoids). The gate token lives
in the OS keychain, never a plain-text file; document a break-glass path
(the owner runs the same script by hand when the scheduled run can't).
`scripts/dcr-gates.sh` is the **one tracked entry point** both `ci.yml` and
the integrator call — no second, undocumented "run every gate locally"
script. The integrator refuses to push without a passing `dcr-gates.sh` run
against that exact head SHA, and **never** honors a `[skip ci]` commit
message on the ref main CI protects (a skip-ci merge into a protected branch
defeats the backstop main CI is there to be).

**Key the `[skip ci]` marker convention to the ref's actual CI state, not a blanket per-commit habit.** On a ref
with **zero GitHub-hosted CI already** (this integration-branch case above), stamping every commit with
`[skip ci]` skips nothing that would otherwise run — it is pure noise, paid on every commit for zero effect. One
observed run: the marker kept firing on commits after CI had already been turned off at the repo level. Drop the
marker entirely on a CI-off ref; add it back only if/when hosted CI is (re-)enabled on that specific ref — this
add-it-back case never applies to a ref main CI protects (the *Cost discipline* rule above, ~L222: `[skip ci]`
is never an option there, CI-off or not). **Check:**
before requiring or emitting the marker, read the ref's actual CI state (branch-protection required-checks list,
or whether any workflow triggers on that ref) — a marker keyed to a stale assumption is the same "protocol claim
with no enforcement behind it" failure this section's Claim-only-the-level-you-observed rule names.

**Hosted CI that cannot actually block a merge is pure cost — verify branch protection before trusting it as a
gate.** A workflow running on every push is spend with zero enforcement value if nothing on the host actually
requires it to pass before a merge lands: no branch-protection rule naming it as a required check, so a red run
never stops anyone. One observed run: roughly 18,000 CI runs over about 25 days with no branch protection
configured; in one 24-hour window only about 25 of 1,000 queued jobs actually started before the account's CI
spend was refused, and disabling workflows one at a time still left two platform-injected default workflows
running. Query the host's actual branch-protection/required-checks state before trusting a green workflow as a
gate — a workflow *existing* and a workflow *enforced* are different claims (the Protocol / Host-enforced split
above). The first fix is to **make it a required check** — add the workflow to branch protection so a red run
actually blocks the merge; that alone converts spend into enforcement, no disabling needed. Only when the
workflow genuinely cannot be made to gate (no branch-protection hook available, or the owner declines) does
disabling apply, and even then **only the gating/test workflows** — leave release, deploy, and security-scan
workflows running unless the owner says otherwise, since those carry value beyond blocking a merge. Disable
**at the repo level, with owner authorization (below)**, not per-workflow — check for platform-injected default
workflows too, since a per-workflow disable can miss them — and replace the check with a **local QA receipt
bound to the merged PR's exact head SHA at merge time** (the `Verify:`-line discipline in
`verification-handback.md`, applied to the merge gate itself), never a hosted run nobody is
required to wait for. Disabling a repo-level workflow is a shared-state, hard-to-reverse change —
confirm with the owner before disabling, per the confirm-before-destructive-action rule.

**Removing hosted CI from an integration branch, and posting required
statuses under a separate identity, both need the repo owner's explicit
authorization and owner-held tokens** — an agent proposes this profile and
stops to ask; the host's own branch protection may otherwise read the
change as a CI bypass and block it regardless of what an agent decides
locally.

A commit **status needs a SHA that already exists on GitHub** — a purely
local merge has no such SHA, and a required check on a protected branch
evaluates the PR head, not an unpublished local merge. The gate first
refuses unless the working tree is exactly the committed HEAD (no unstaged,
staged, or untracked changes — a `--no-commit` staging area is not a
committed result), fetches the target branch fresh (never a stale cached
ref) and fails closed if no base is resolvable. So the flow is: push the
gated SHA (never a moving `HEAD`) to a scratch ref (`refs/integrator/tmp`,
force-pushed each cycle — it is disposable), run the gate against that
pushed SHA, post the status on it, and only then **fast-forward** the
protected branch to that same SHA (a plain, non-forced push — git itself
refuses a non-fast-forward, so a stale or diverged integrator run can never
silently overwrite history). Both pushes are performed AS the push identity
— authenticated via a credential helper, not read out of an env var and
merely compared by name — so "separate identity" is a property of the push
itself, not a second, self-asserted variable. If the branch's protection
needs a required status, it is posted by a **separate gate identity** from
the one that pushed — a status minted by the pusher's own token is forgeable
(any push-access credential can POST any commit status for any SHA) and
proves nothing about whether a gate ran; `templates/integrator-gate.sh`
refuses to post when the gate token's `gh api user` login equals the push
token's. Pre-push hooks (`pre-push-verify.sh`) are convenience, not
enforcement — they are self-report, bypassable by `--no-verify` or a
repointed hook.
**The local gate is not evidence unless it runs in the same OS/toolchain as
main CI** — GNU vs BSD coreutils, shell built-ins, and line-ending handling
differ enough that a macOS-only local pass proves nothing about a Linux-runner
result. `ubuntu-latest` is a VM image, not a published container, so "the
same image main CI uses" is only true once main CI itself declares a
`container:`. Pin **one multi-arch image by digest** and use it both as main
CI's `container:` and locally (`docker run`/`colima`/OrbStack — do not assume
Docker Desktop's organization licensing applies; verify it for the actual
operator). Apple Silicon runs an `arm64` pull of that digest natively while
`ubuntu-latest` is `amd64` — document that arch gap rather than hiding it;
main CI is what catches an arch-specific bug, the local run is not a
substitute for that coverage, only for the rest of the gate.

**Main/release:** hosted CI runs only on PRs into the default branch.
`pull_request` trigger `types: [opened, reopened, ready_for_review,
synchronize]` — omitting `opened`/`reopened` means a PR opened directly as
ready (never drafted) gets no initial run at all, only on its next push; a
job-level `if:` still skips a draft (drafts stay skipped — a draft's checks
would burn minutes on work not yet ready for review), which is the actual
gate, not the trigger's `types:` list. Workflow-level `concurrency` with
`cancel-in-progress: true` (safe
because a branch gets one final push per PR before merge); every job carries
`timeout-minutes`. No `push` trigger, no post-merge run, no `schedule:` by
default (weekly at most, for probes only — a daily-or-more-frequent cron
burns minutes with no PR for a reviewer to object to). A required check's
workflow is never `paths`/`paths-ignore`-filtered or workflow-level
conditional — an unmatched filter means the check never reports, so the PR
blocks forever "waiting for status"; scope with a job-level `if:` that still
reports success/skip instead. Consolidate jobs into fewer workflows —
GitHub rounds every job's minutes **up** to the next whole minute, so five
10-second jobs bill as five minutes. Linux runners unless a job genuinely
needs Windows/macOS (macOS bills at roughly 30x a Linux 1-core minute).

**Synthetic probes & uptime checks are monitoring, not CI** — never solve
their cost by cutting how often they run (that degrades detection time, the
thing they exist for). Move them to free infrastructure that isn't billed
runner-minutes: a local `cron`/`launchd` job, or a free tier of a dedicated
uptime monitor, at their **original** cadence. A local scheduler has no
dead-man switch of its own — a laptop that sleeps or a probe process that
dies goes silent with nobody noticing the watcher itself is gone. Using only
free tools: on a probe failure, `gh issue create` (GitHub's own free email
notification, zero Actions minutes — an optional `ntfy.sh` push is extra,
not required); every probe run, pass or fail, writes a heartbeat (a
timestamp file or an updated issue/gist). A GitHub Actions `schedule:` stays
at the doctrine's own cap (none, or weekly) and is used **only** to check
that heartbeat is fresh — failing loudly (a new issue, a red check) when it
has gone stale — never as the frequent prober itself.

**Self-hosted runners:** compute is free (no included-minute draw, no
per-minute charge, regardless of repo visibility) — but only inside a
disposable VM/container with no host secrets and restricted egress, ephemeral
or JIT (one job, then torn down). Never on the bare host for a job that
executes untrusted or agent-ingested content (a scraped doc, a dependency
README, a prompt-injected issue) — GitHub's own guidance that self-hosted
runners on private repos are compromised by "anyone who can fork the
repository and open a pull request" describes the fork-PR threat; an
agent-authored-code threat is broader (the agent itself can be coaxed into
emitting exfiltrating code) and needs isolation regardless of PR trust level.

**Merge queue:** only available on a public repo, or a private repo **owned
by an organization on GitHub Enterprise Cloud** — not Team, not Pro, not a
personal-account repo. Verify plan and ownership before relying on it; where
unavailable, a merge train (`merge_train.py`) is the mechanized substitute
(see `references/merge-queue-worktrees.md` — not restated here).

**Spend backstop:** a soft budget (alert-only, never a hard stop that could
block legitimate CI) — configure alerts at 50/80/100% of the cap so an
operator sees the trend before it bills out, not just at the limit.

**Tokens:** cheapest model tier that fits the task (`CLAUDE_CODE_SUBAGENT_MODEL`
above); per-lane tool-call caps; no reminder/poll loop firing more often than
every 20 minutes; never poll a merge (`gh pr merge --auto` schedules the
merge server-side instead of a loop re-checking status); `token_report.py
--budget` before a paid run, not after. **Cost cuts never apply to review
depth on a security-critical or gate/enforcement change** (anything that
grants merge/push rights, mints a credential, or changes what a gate checks)
— that review keeps the strongest available model plus an independent
reviewer; the cheapest-tier default is for mechanical lanes (formatting,
boilerplate, a routine dependency bump), not for judging whether a control
actually holds.

**A lane that hits its tool/token cap mid-task hands back a checkpoint, never
a "done" claim.** The handback states what ran, what did not, and marks the
result `UNVERIFIED` for whatever gate it could not complete — the caller
re-dispatches the remainder instead of trusting a claim the lane had no
budget left to earn. This is the same claim-honesty rule the top of this file
applies everywhere else: a check that could not run is `UNVERIFIED`, never a
pass.

**A rule moved out of a must-load file needs an eval proving its trigger
fires** — a routed `references/*.md` with zero evals citing it is unproven
prose, the same gap `docs/standards-index.md`'s routing rule closes for
"is it findable" but not for "does it work." `scripts/eval_citation_lint.py`
(repo root, `--selftest`-backed) flags exactly that: a references file this
skill's `SKILL.md` routes to, that no eval in the skill's `evals/evals.json`
cites by name. It is advisory today, run per-skill (`eval_citation_lint.py
<skill-dir> [--gate]`), not yet wired into the repo-wide gate — several
skills' reference files predate this check and are not yet retrofitted with
citing evals; that backlog is a deferred, named follow-up, not silently
closed. Both evals this section itself added
(`agentic-delivery/evals/evals.json`) cite `host-enforcement.md` by name, so
this file passes the check today.

Sources (fetched 2026-09-24): GitHub Docs — Billing and usage
(`docs.github.com/en/actions/concepts/billing-and-usage`, self-hosted runner
usage is free regardless of repo visibility); GitHub Docs — Actions runner
pricing (`docs.github.com/en/billing/reference/actions-runner-pricing`,
per-job minute rounds up, per-minute OS rates); GitHub Docs — Secure use
reference (`docs.github.com/en/actions/reference/security/secure-use`,
fork-PR self-hosted-runner compromise risk); GitHub Docs — Managing a merge
queue (`docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue`,
org + GitHub Enterprise Cloud gate on private repos); GitHub Docs — Commit
statuses (`docs.github.com/en/rest/commits/statuses`, any push-access token
can post any commit status for any SHA). Full verification detail in
`docs/standards-index.md`. **By name only, not re-verified this session:**
`gh issue create`'s email-notification behavior, GitHub Actions `container:`
digest pinning, and Docker Desktop's organization-licensing terms — confirm
current behavior/terms before treating any of the three as a fetched fact.

## Opt-in: terse-reply Stop hook and scope-creep warning

Two deterministic, generic checks, both off by default. Neither vendors any chat-voice text; for a compressed chat style see the public caveman repository (https://github.com/JuliusBrussee/caveman).

- `scripts/terse_reply_check.py` runs on `SessionStart` (prints the reply budget, so the first draft fits), `Stop` and `UserPromptSubmit`. A reply over `TERSE_MAX_LINES`/`TERSE_MAX_CHARS` (3/500) or a filler/article/hedge share above `TERSE_MAX_RATIO` (0.12; under `TERSE_MIN_WORDS`=25 skipped) does not block: the next prompt gets a one-line reminder, so the user never sees a duplicate. Code blocks, inline code and `! ` lines are not counted. `TERSE_MODE=block` restores the `{"decision": "block", ...}` rewrite (`stop_hook_active` allows one per turn). Enable with `install.sh --with-delivery --with-terse-replies`, which writes `.claude/settings.terse-replies.json.new` to merge by hand.
- `scripts/scope_creep_check.py BASE HEAD` is warn-only (always exits 0). It lists new files, new dependencies (`package.json`, `requirements*.txt`, `pyproject.toml`, `go.mod`, `Cargo.toml`) and new classes or interfaces with exactly one implementation, against the touched-file count. The regexes are heuristics: a lead for the reviewer, not a verdict. `pre-push-verify.sh` runs it when the script is installed.

## Deferred-question hooks (optional, advisory)

**Advisory, not Host-enforced:** they never block and never continue a turn.
`agentic-ceo/scripts/stop_reminder.py` — **use this when** an autonomous run
has stalled on a question the absent owner could not answer while other work
remained. A notice is due when a `task_ledger.py defer` question is pending and
an open or doing row exists. The hook event picks the output (hooks reference,
`docs/standards-index.md`, 2026-09-24):

- `SessionStart` / `UserPromptSubmit`: **model-visible** —
  `hookSpecificOutput.additionalContext` says "pending deferred questions: N;
  next non-gated item: T-###" at turn start.
- `Stop`: an **owner-facing** notice via `systemMessage` ("Warning message shown
  to the user"); the model is not guaranteed to see it.

Any failure (missing module, bad input, malformed file, crash) prints nothing
and exits 0. The snippet adds `|| true` and a short `timeout`, so even a missing
script cannot exit 2, which would block `Stop`. The owner can still stop the
agent or answer. `--selftest` proves each branch. The owner installs it by
hand; `install.sh` never edits settings:

```json
"hooks": {
  "UserPromptSubmit": [
    { "hooks": [{ "type": "command", "timeout": 5,
        "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/agentic-ceo/scripts/stop_reminder.py || true" }] }
  ],
  "Stop": [
    { "hooks": [{ "type": "command", "timeout": 5,
        "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/agentic-ceo/scripts/stop_reminder.py || true" }] }
  ]
}
```


## When agents may not commit, push, or edit agent-rule files

- **No-commit repos.** Where agents may not commit or push, the standard hand-off is: stage the changes, print the exact hand-off commands, and write each PR body to a file, batched across worktrees. Push everything first, confirm with a remote-ref check, and only then create PRs, passing an explicit `--base` for stacked PRs; creating a PR before a slow hook finishes the push races it.
- **Host classifiers block self-modification.** In auto mode a host safety classifier can refuse an agent's commit of agent-instruction files (`AGENTS.md`, `.claude/agents/*`) even when the owner authored them. Ship such a rollout as an install-script step the owner runs; never have an agent commit it.
- **Prefer fixup commits to amend.** The same classifiers treat amending an unpushed commit as destructive, so doctrine should say fixup commit, not amend.
- **Toolchain preflight.** Before gates run, check that each required tool resolves on `PATH` (a package manager supplied by a shim such as corepack often does not); a missing shim otherwise surfaces as an opaque hook failure.

## Committed Perun copy stays current (auto-update PR)

Background auto-update (`scripts/perun_auto_update.py`) rewrites only the main clone's working tree. The Perun
copy committed on the integration branch then stays old, so every lane worktree and fresh checkout (branched from
it) runs old skills. With policy `auto_update_pr: on` (the default; `off` opts out) the same worker, after an update
or an up-to-date check, opens a PR that commits the install marker's recorded managed files (skill files and slash commands; never untracked files or symlinks) to `perun/update-v<ver>`. It works in a throwaway detached worktree off `origin/<default>` (or `origin/<auto_update_pr_base>` when that policy key names the integration branch; a base missing on origin skips the PR, never guessed; the WARN below compares against the same base), so the user's
checkout and uncommitted work are never touched; pushes without force; opens the PR with `gh pr create`, falling back
to `gh_rest.py`'s curl path; never merges; commit/push hooks are never bypassed but time out after 30 min (`hooks timed out`, logged). It skips when the committed version already equals the installed one,
when an open PR for the branch exists (a pushed branch with no PR only gets its PR retried), or when nothing differs, and logs the outcome to `auto-update.log`. Failures
stay silent to the agent and never block the session. Read-only detection: `session_brief.py` and
`operating_selfcheck.py` WARN `committed Perun vX < installed vY: lanes in other worktrees run old skills;
open/merge the perun/update PR` when `git show <default>:.claude/skills/deep-code-review/VERSION` is behind the
working tree. Merging that PR is the human's call (protocol, not enforced).

On a shared host run local hook and test runs under `nice -n 19` with capped workers (`pre-push-verify.sh` does; a test runner's worker count is at most a quarter of the cores), give any test fixture that spawns CPU load a guaranteed teardown that the orphan reaper's pattern also matches, and never let a throughput alarm recommend more trains or parallelism before it has read `load1`.

- **A merged host installer is inactive until the owner applies it.** The change that needs a host-side install announces a fixed, named installer (`scripts/host_installer.py announce global-rules <repo-root>`; the command is built by the script, never passed in) and the owner gets one line, `! <command>`, to paste; `install.sh --global-rules` marks it applied, and `perun_auto_update.py` announces it after an update that changed the rules scripts. Never auto-run it and never bypass a permission prompt or classifier. Set policy `installer_unapplied_h` (hours, 0 = off) and the landing watchdog warns "Installer unapplied: ..." when it stays unapplied; a corrupt state file alarms too and is copied aside before it is replaced.
