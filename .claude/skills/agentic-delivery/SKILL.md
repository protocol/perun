---
name: agentic-delivery
description: >-
  Use when implementing a feature, migration or end-to-end change: build, add,
  ship, deliver, fix a ticket. Invoke FIRST, before inspecting files, even
  if the dir looks empty. Gated delivery: independent QA and security, one
  writer per worktree, human approval on push/merge/deploy. Not a typo fix.
license: MIT
metadata:
  author: deep-code-review contributors
  version: "1.626.0"
---

# Agentic delivery

Gated-delivery **pattern**, not a runtime or standing swarm. Does not replace `deep-code-review` (review is the bar; this is how work reaches it); one delivery OS per repo. Persisted artifacts are normal English. No files/tools? Say so once, never claim a reference loaded or a command run: write `would run: <cmd>`, mark `unverified-depth`. Full gate table, roles, worktree, human-gate, failure text: `references/full-map.md`.

**Task to entry** — a match skips `INDEX.md`; else read it and open only matching rows.

| Task | Open (bare `*.md` = `references/`) |
|---|---|
| Land PRs as a train; red gate or union | `scripts/merge_train.py`, `scripts/train_land.sh`, `merge-queue-worktrees.md`; `gate-epistemology.md`, `red-gate-triage.md`; `flow-guards.md` (dedupe hook, fitness check, flow alarms, freeze) |
| Start a lane; isolate its worktree | `templates/lane-preamble.md` in every brief; `worktree-isolation.md`, `roles.md`; `templates/loops/` |
| Verify or relay a result; slow pipeline | `verification-handback.md`; `pipeline-optimizer.md` |
| Long session, compaction, new session, memory or docs bloat | `references/focus-kit.md`: update `.claude/handoff.md` (`scripts/focus_kit.py handoff set`) at each gate, before a context-heavy step, before handback |
| New machine or fleet | `operating-discipline.md` |
| Audit a repo's GitHub settings (branch protection, Actions token, deploy keys, webhooks) | run `python3 scripts/repo_settings_audit.py OWNER/NAME... [--repos-file FILE] [--json]`: read-only, a 403 or 404 is `not checked`; admin token for the full set |
| PR state; hand off; changelog | `scripts/pr_state.py <n>`; `scripts/land_ready.py` (open PRs ready to land, or why not); `scripts/review_status.py --sha S --red N` (post `perun/review`); `scripts/premise_check.py <n>...`; `scripts/ci-gates.sh fragments` |
| Cost cut, lane cap; "enforced" claim, CI cost | `cost-quality-guardrails.md`; `host-enforcement.md` |
| Fan-out size, host probe | `fanout-host-sizing.md`, `fast-agentic-delivery.md` |
| Dev server, local stack | `dev-env-ownership.md` |
| Resume, durable state; peer sessions | `project-state.md`; `multi-session-coordination.md` |
| Tracker, auto-close, multi-hour loop | `work-tracking.md`, `unattended-trackers.md`, `unattended-operating-mode.md` |
| Product surface; ADR; brief | `production-grade-product-playbook.md`, `template-adr.md`, `template-onepager.md` |
| Incident, support; G10, postmortem; install | `incident-response.md`, `support-ops.md`; `retrospective.md`, `template-postmortem.md`; `install.md` |
| scripts | `scripts/review_gate.py`, `flake_ledger.py`, `focus_kit.py`, `handback_cap.py`, `heavy_gate.py`, `operating_selfcheck.py`, `outcome_claim_guard.py`, `pipeline_profile.py`, `queue_guard.py`, `serial_gate.py`, `session_brief.py`, `wired_check.py`; `templates/review-tiers.tsv` |

Open `references/full-map.md` for multi-lane work, a red gate, host sizing, an unattended loop or a human-gate edge case. Sections cited as "SKILL.md <section>" (Conductor operating rhythm, Worktrees and occupancy, Local environment, Environment probe, Gate epistemology, Output contract) now live there.

## When to Use

Use when a change spans build plus QA or security, writers would collide, or the owner asked for a feature, migration or release; not a typo. Load `idea-critic` before any agent-originated "we should" reaches the owner.

## Hard rules

- Smallest sufficient team, hats from risk. The Conductor never self-approves. A builder never reviews builder and never wears QA, security or release-approval. Physical or social-engineering security is human-led under written ROE.
- Conductor reacts to a blocked gate, receipt, budget breach or collision; never does a lane's work. After two equivalent failures change approach.
- Low-blast work may collapse adjacent gates; it may not remove independent verification or an applicable human approval.

| Gate | Hard condition |
|---|---|
| G0 Intake | Goals, non-goals, appetite; `idea-critic` first. Shape `references/template-onepager.md` |
| G1 Spec | Acceptance criteria, `deep-code-review` scope, pinned base SHA |
| G2 Plan | One writer per worktree; every paid lane names a token/dollar budget before G4, none is blocked |
| G3 Design | ADRs / contracts: interfaces, NFR budgets, data/security decisions explicit. Shape `references/template-adr.md` |
| G4 Implement | Tests before or with the change |
| G5 Verify | Local = affected tests; CI on the exact SHA is the receipt; UI needs headed-browser evidence |
| G6 Review | Independent of builder; Blocker/Critical block, High needs a named owner |
| G7 Integrate | One owner; CI on the exact final SHA |
| G8 Release | Rollback proven; **owner approves** outward/production action |
| G9 Prod verify | Served SLOs; rollback on breach |
| G10 Learn | Escaped gap becomes a regression test; strip third-party identifiers |

**Missing evidence is `UNVERIFIED`, never pass. Missing price is `UNPRICED`, never zero. Missing spend cap is `BLOCKED`, never unlimited.** A lane's completion is G7; G8 is separate and owner-gated.

## Exact revision

Every packet names `deep-code-review`, its scope (`FULL`/`DIFF <base>`/`FILE <paths>`) and the base or reviewed SHA. QA and security get the final SHA; a stale SHA fails closed.

## Worktrees

One writer per worktree; assume a shared tree until proven isolated. Preflight: list worktrees and open PRs, claim the work, never duplicate a running lane. Use the repo's own script for repeatable steps. A child lane branches off the parent's local ref, never polls the remote. Spawn a heavy lane only while free RAM >15% and swap is flat (`scripts/host_probe.py`).

## Human gates

Agents prepare; humans approve push, open/merge PR, publish, deploy, external replies or refunds, scopes/secrets/IAM, destructive migrations, force-push, flag flips, waiving a Blocker/High finding.

**Standing grant.** A grant counts only from an owner-authored artifact: the owner's own commit (author = owner) to `CLAUDE.md` or the state record, or their message quoted verbatim with date. The agent never creates, widens, extends, or re-dates a grant. Absent or ambiguous means gated. A merge that triggers deploy or publish is a deploy, never covered. Force-push, history rewrite, deploy, secrets, spend, external sends and destructive data stay gated. Park a gated item with its next step and continue.

Ask as `Issue:` one line, `A:` (recommended), `B:`, ≤12 words each; never a list of questions.

## Output and failure

Workers return role, exact SHA, artifacts, commands run with exit status, findings with severity and location, remaining risk, cost or `UNPRICED`. A work item needs **Where**, **Done-when**, **Verify**, **Why**; missing Done-when or Verify is sent back.

A start or auth failure is no work done. **A running lane is not a finished one.** Done means verified — a green gate at the exact SHA. A model outage fails the lane closed. No uncommitted writer work without a recovery record.
