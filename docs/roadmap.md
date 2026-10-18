# Roadmap

Two parts. The **product roadmap** below is what to build or fix next for Perun, produced by the CEO
[improvement loop](../.claude/skills/agentic-ceo/references/improvement-loop.md): ranked by a printed formula from
sourced-or-assumed inputs, with a success metric, evidence links, ADRs and tracker-ready issues. The
[suite design record](#agent-suite-roadmap-proposed--living) after the divider is the 2026-09-11 design of the agent suite, kept unchanged.

To regenerate, edit [`roadmap-input.json`](roadmap-input.json) and run
`python3 .claude/skills/agentic-ceo/scripts/roadmap_rank.py docs/roadmap-input.json --update docs/roadmap.md`.
`scripts/test_roadmap_rank.py` fails when this page and its input drift apart.

<!-- roadmap:begin -->
**BLUF.** Stage `mvp` (assumed). 22 items ranked (15 open, 7 in flight), 6 rejected. Top: `sandbox-preflight` 3.75 (in flight), `gate-cache-tree-sha` 3.75 (in flight), `autonomy-advisor` 3.33. Start now (highest-ranked open item with no gate): `autonomy-advisor`. 12 of 22 reach inputs are assumed; equal scores rank fewer assumed inputs first.

## 1. Strategy context

As of 2026-10-16. A source that starts with **assumed** is an explicit assumption, not a repo fact.

| Field | Value | Source |
|---|---|---|
| stage | mvp | **assumed**: no repo doc states a stage. Signals: version 1.586.0, a public MIT repo, CI, gates and evals in place, a small set of peer operators (survey:2026-10-16), no retention or product-market-fit data and unverified adoption (docs/perun-vs-rivals.md section 3), no product skill ahead on a rubric-free judge (H1c, H1d). A growth stage needs a product-market-fit read (product-discovery); none exists. |
| vision | One solution across code review, token optimisation, delivery, product work and C-suite advice, measurably better than rival bundles in each area, with every claim kept inside the evidence. | owner:2026-10-16 (stated goal). README.md states the review-first version and docs/roadmap.md the suite version (honesty, verification, stage-awareness). |
| north star | Tokens per delivered, gate-green PR, with review quality (F1 on the public case set) held constant. | **assumed**: no repo doc names a north star. Closest instruments: .claude/skills/agentic-ceo/scripts/token_ratchet.py (tokens per delivered PR) and the review F1 in docs/perun-vs-rivals.md; neither is measured across installs, because there is no telemetry. |
| direction | Close the measured gaps against rivals (review cost at equal quality; product skills that win no rubric-free comparison), remove the delivery friction peers report, and keep every claim inside the evidence. | docs/roadmap.md (suite direction and epistemic spine), docs/perun-vs-rivals.md (measured gaps), survey:2026-10-16 (peer pain points) |
| constraints | No paid model benches in this pass. Instructions, not a service: no telemetry. No fabricated evidence; the privacy and no-duplication rules apply. In-flight work is listed, not re-ranked. | owner:2026-10-16 (no paid benches); README.md (Safety: instructions, not a service); CLAUDE.md (hard rules) |

Owner question (one batch): confirm or correct the assumed stage, north star. The run continues on the assumption; a correction re-runs this script.

Evidence base (a source that was absent or unreadable is listed as such, never skipped):

- Run mode: CEO direct. One agent applied the CPO, CTO, CFO, CMO, CISO and COO briefs in turn to the same evidence and spawned no lanes, because the evidence fits one context and a fan-out would only add cost. The CISO lens found no open item with a security lever that clears the evidence bar; its host-safety concerns are folded into janitor-teardown-land and handback-automator.
- Peer survey, 2026-10-16, rows P1 to P10, and field measurements F1 to F3, committed as docs/peer-survey-2026-10-16.md: an operator-supplied relay, not a measurement made in this repo, without per-item counts. P1 hook reruns of 2 to 15 minutes; P2 gates run 3 times per tree; P3 the sandbox blocks gh, Chromium, Postgres and tsx IPC; P4 lanes end their turn while background tests still run; P5 flaky tests drop PRs from trains; P6 a pr_state one-shot command is wanted; P7 a lane-handback automator is wanted; P8 a sandbox preflight is wanted; P9 reply-cap rewrites; P10 re-deriving state after compaction. F1 a 47-minute hook cycle fell to 30 seconds with gate dedup; F2 about 5 sandbox retries per session; F3 zero-chat lanes, no measurement. A survey row or relayed number counts as a source for an input, but reach stays a hypothesis until counts exist.
- GitHub issues and PRs for protocol/perun, REST API, fetched 2026-10-16: 14 open issues (61, 69, 267, 273, 393, 1316, 1380, 1418, 1430 to 1433, 1530, 1531) and 1 open PR (1382, last updated 2026-10-07). No open PR exists for any in-flight item the owner named, so those statuses are owner-stated and unverified on GitHub.
- CHANGELOG.md, releases 1.584.0 to 1.586.0 (merge-train flake rules, extra hosts, auto-compact with handoff re-inject): read to reject work that already shipped.
- docs/perun-vs-rivals.md: the repo's own benchmarks H1 to H11 and the rival gaps in section 3. Review ties the Anthropic toolkit at about 3.5 times the cost, and no product skill beats its rival on a rubric-free judge.
- Rival and platform changelogs, fetched live 2026-10-16: obra/superpowers releases v7.0.0, v6.4.2, v6.4.1 and v6.3.0 (GitHub releases API) and the Claude Code CHANGELOG.md, top entry 2.1.301 (raw.githubusercontent.com). UNVERIFIED: gstack releases and the Claude Code release pages, because the unauthenticated GitHub API rate limit was hit; not retried.
- Not present: analytics (Perun is instructions, not a service and has no telemetry), support threads and a user-feedback file. Not read: session logs (private by default); token_report.py and weekly_receipt.py are the instruments for an operator's own repo. docs/capability-matrix.md does not exist at origin/main c097d01f (checked 2026-10-16), so it was not used.

## 2. Rejected items

| Item | Rule | Reason |
|---|---|---|
| `usage-telemetry` Opt-out usage telemetry to measure reach | vision: misaligned | Breaks a stated constraint: Perun is instructions, not a service (README.md, Safety). The cheaper route to measured reach is a survey with counts (peer-survey-v2) and the operator-local receipts that already exist (weekly_receipt.py). |
| `rederive-state-after-compaction` Re-derive state after compaction (survey P10) as a new feature | CEO decision | Already shipped: auto-compact with handoff re-inject (CHANGELOG.md 1.586.0, handoff_inject.py) and the task ledger (task_ledger.py). The remaining gap is PR state, covered by the in-flight pr-state-one-shot. |
| `compact-card-recall-variants` More compact-card variants to recover review recall | CEO decision | A measured dead end: the best of three variants failed on the held-out half (n=22, F1 -0.036, interval -0.194 to +0.095, H7), and the real skill already ties the toolkit on recall (H7b). Reopen only with a new idea and a held-out plan. |
| `own-output-safety-eval-runner` Build a product-output-safety eval runner inside Perun | CEO decision | Better way, registry not a bundle: an existing tool already runs evals and red-team scans in CI (promptfoo, section 3). Ship a config template only if the H1b loss is shown to come from missing tooling; that test comes first (differentiator-bench). |
| `host-count-expansion` Add more native hosts | CEO decision | Breadth before depth: 18 of the 19 listed hosts were never run on a real host (H10) and the one open candidate, Muse, had no vendor docs (CHANGELOG.md 1.585.0). At mvp the stage weights favour verifying what is listed (real-host-smoke-tests). |
| `session-diagnosis-skill` Add a session-diagnosis skill, as a rival did | CEO decision | Deferred on evidence, not rejected on merit: one rival release is a lead, not user evidence (product-discovery riskiest-assumption gate), and token_report.py covers spend, not causes. One question goes into peer-survey-v2 (how is a failed session diagnosed today?); reopen on the answers. |

## 3. Ranked roadmap

Score = reach × impact × confidence ÷ effort × stage weight × vision factor. The score orders the list, it does not prove anything. The loop scores itself, so every input that is not backed by a real link or repo path is listed as assumed below.

- reach 1-5: share of our own users or runs touched, 5 = every one (never a market size; an item that only helps later rankings has no reach)
- impact 0.25, 0.5, 1, 2 or 3: minimal, low, medium, high or massive effect on the north star
- confidence is computed: 1 when reach and impact both cite a URL, an existing repo path or an issue or PR, else 0.5; `assumed`, `estimate:` or any other text counts as assumed
- effort: lane-days, plus 2 per owner or external-send gate and 0.25 per calendar-wait day
- stage weight: lever × stage from the table below; the active stage is `mvp`
- vision factor: aligned 1.0, partial 0.5; a misaligned item is rejected in section 2
- items already in flight are scored and flagged, not dropped; equal scores rank fewer assumed inputs first, then lower effort, then id

| lever | prototype | mvp (active) | growth | mature |
|---|---|---|---|---|
| learning | 1.5 | **1.5** | 1 | 0.75 |
| reliability | 1 | **1.25** | 1.5 | 1.5 |
| velocity | 1.25 | **1.25** | 1 | 0.75 |
| growth | 0.25 | **0.5** | 1.5 | 0.75 |
| scale | 0.25 | **0.5** | 1.25 | 1.5 |
| cost | 0.5 | **0.75** | 1.25 | 1.5 |
| polish | 0.25 | **0.5** | 1 | 1.25 |
| security | 1.5 | **1.5** | 1.5 | 1.5 |

| # | Item | Status | Lane, lever | Score | Success metric | Evidence | Gate |
|---|---|---|---|---|---|---|---|
| 1 | `sandbox-preflight` Sandbox preflight for gh, Chromium, Postgres and tsx IPC, with the reply-cap code-block exemption | in flight | -, reliability | 3.75 | Blocked-tool surprises per lane from 4 named tools (survey P3) to 0 unreported: one verdict line per tool before work starts; reply-cap rewrites (survey P9) counted before and after the code-block exemption lands. | survey:2026-10-16#P3; survey:2026-10-16#P8; survey:2026-10-16#P9; [sandbox_probe.py](../.claude/skills/agentic-delivery/scripts/sandbox_probe.py); [gh_rest.py](../.claude/skills/agentic-delivery/scripts/gh_rest.py); https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md | - |
| 2 | `gate-cache-tree-sha` Shared tree-SHA gate cache with gate_map and light-lane weighting | in flight | -, velocity | 3.75 | Hook cycle 47 minutes to 30 seconds and gate runs per tree 3 to 1 (field report F1; survey P1, P2); report the numbers when it lands. | survey:2026-10-16#P1; survey:2026-10-16#P2; [pre-push-verify.sh](../.claude/skills/deep-code-review/templates/pre-push-verify.sh); [preflight.py](../.claude/skills/agentic-delivery/scripts/preflight.py) | - |
| 3 | `autonomy-advisor` Autonomy advisor: read the sandbox and permission settings and print the narrow rules that stop sandbox retries, never writing settings | open | COO, reliability | 3.33 | Sandbox-blocked retries per session: about 5 (field report F2) to 1 or fewer; one printed rule per probed failure, 0 settings files written. | [peer-survey-2026-10-16.md#f2](../docs/peer-survey-2026-10-16.md#f2); [peer-survey-2026-10-16.md#p3](../docs/peer-survey-2026-10-16.md#p3); [sandbox_probe.py](../.claude/skills/agentic-delivery/scripts/sandbox_probe.py); [host-safety.md](../docs/host-safety.md) | - |
| 4 | `pr-state-one-shot` pr_state: one command for a PR's checks, mergeability and review state | in flight | -, velocity | 1.88 | Commands needed to learn a PR's state from several gh calls (survey P6) to 1; state after a compaction read in 1 call (survey P10). | survey:2026-10-16#P6; survey:2026-10-16#P10; [gh_rest.py](../.claude/skills/agentic-delivery/scripts/gh_rest.py) | - |
| 5 | `handback-automator` Lane-handback automator: gates, required-check names, base-branch fast-forward and tracker post; cleanup printed, never run | open | COO, velocity | 1.25 | Manual steps per handback: 6 (lane-preamble.md: wait, handback, clean_finished.sh, reap_own.sh, changelog fragment, git diff --check) to 1; handbacks needing a second pass: unmeasured, count for 2 weeks. | survey:2026-10-16#P7; [lane-preamble.md](../.claude/skills/agentic-delivery/templates/lane-preamble.md); issue:#1530; issue:#1531 | - |
| 6 | `low-context-skill-index` Low-context skill index | in flight | -, cost | 1.25 | Always-loaded tokens, full install 921 and review-only install 75 (section 2), and review cost per case $0.0537 (H7b): report all three after it lands; the routing eval stays at 24 of 30 (H3). | [perun-vs-rivals.md#2-always-loaded-toke…](../docs/perun-vs-rivals.md#2-always-loaded-token-overhead-static-count-2026-10-15); [perun-vs-rivals.md#h7b-review-patch-onl…](../docs/perun-vs-rivals.md#h7b-review-patch-only-the-real-skill-against-anthropic-toolkit-2026-10-16); [INDEX.md](../.claude/skills/INDEX.md) | - |
| 7 | `background-work-guard` Block a handback while any background test or build from the worktree is still running | open | COO, reliability | 0.94 | Lanes handing back with a live background process: unmeasured now (survey P4), target 0; the guard blocks the planted fixture 1 of 1. | survey:2026-10-16#P4; [handback_cap.py](../.claude/skills/agentic-delivery/scripts/handback_cap.py); [lane-preamble.md](../.claude/skills/agentic-delivery/templates/lane-preamble.md); issue:#1530 | - |
| 8 | `janitor-teardown-land` Land the worktree janitor (PR 1382, open since 2026-10-07) and the teardown standard (issue 1531) | open | COO, reliability | 0.94 | Finished worktrees and leftover dev servers at session start: 130 or more in the field report behind session_brief.py, target 0 after a train; PR 1382 age 9 days to merged or closed. | pr:#1382; issue:#1531; [session_brief.py](../.claude/skills/agentic-delivery/scripts/session_brief.py); https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md | - |
| 9 | `flake-ledger-quarantine` Per-test flake ledger with quarantine, so flaky tests stop dropping PRs from trains | open | COO, reliability | 0.83 | PRs parked as flake-blamed per 100 train PRs: unmeasured now (survey P5), measure for 2 weeks then target 1 or fewer; tests with 2 or more intermittent failures listed in a ledger: 0 now. | survey:2026-10-16#P5; [perun-vs-rivals.md#h11-merge-train-15840](../docs/perun-vs-rivals.md#h11-merge-train-15840); [train_flake.sh](../.claude/skills/agentic-delivery/scripts/train_flake.sh) | - |
| 10 | `zero-chat-lanes` Zero-chat lanes: a lane's chat is one status line, everything else goes to files | open | CFO, cost | 0.75 | Chat tokens per lane run: unmeasured (F3 supplies none); measure with token_report.py first, then target half; final message already capped to 1 line by handback_cap.py. | [peer-survey-2026-10-16.md#f3](../docs/peer-survey-2026-10-16.md#f3); [handback_cap.py](../.claude/skills/agentic-delivery/scripts/handback_cap.py); [lane-preamble.md](../.claude/skills/agentic-delivery/templates/lane-preamble.md) | - |
| 11 | `differentiator-bench` Benchmark the claimed differentiator (refusing to fabricate) with deterministic predicates, not a rubric judge | open | CPO, learning | 0.75 | Bait-prompt pass rate, Perun vs the best rival, graded without a model: unmeasured now; n of 20 or more with a 95% interval; claim superiority only if the interval excludes 0. | [roadmap.md](../docs/roadmap.md); [self-improvement.md](../docs/self-improvement.md); [eval_predicates.py](../scripts/eval_predicates.py); [perun-vs-rivals.md#h1d-idea-critic-prod…](../docs/perun-vs-rivals.md#h1d-idea-critic-product-discovery-and-growth-analytics-re-tests-rubric-free-blind-judge-2026-10-16-425-of-a-6-cap-preregistered-in-docsbenchskill-rubricfree-1016) | owner: a small paid run under a cap, and a rival skill installed |
| 12 | `review-cost-per-recall` Cut review cost per unit of recall: ratchet the review path's tokens, then re-bench once | open | CFO, cost | 0.62 | Review cost per case at equal F1 vs the Anthropic toolkit: 3.5x ($0.0537 vs $0.0153, n=22, H7b) to 2x or less; web-archetype must-load ceiling 20,049 estimated tokens, ratcheted down. | [perun-vs-rivals.md#h7b-review-patch-onl…](../docs/perun-vs-rivals.md#h7b-review-patch-only-the-real-skill-against-anthropic-toolkit-2026-10-16); [README.md](../README.md); [mustload-budgets.tsv](../scripts/mustload-budgets.tsv); https://github.com/obra/superpowers/releases/tag/v6.4.1 | owner: the paid re-bench |
| 13 | `host-command-hints` Host-aware command, model and effort hints | in flight | -, reliability | 0.62 | Hosts with a hint verified on a real host: 1 of 19 at the start (H10); report the new count when it lands. | owner:2026-10-16; [perun-vs-rivals.md#h10-install-and-upda…](../docs/perun-vs-rivals.md#h10-install-and-update-15830-timings-measured-on-15820-host-and-uninstall-fixes-from-the-15830-release-checks) | - |
| 14 | `derived-numbers-gate` Extend the numbers-need-a-source gate from the leaders page to the README and the rivals page | open | CTO, reliability | 0.62 | Pages under the digit-needs-a-source rule: 1 of 3 now (docs/for-leaders.md only), 3 of 3. | [check-leader-doc.sh](../scripts/check-leader-doc.sh); [perun-vs-rivals.md](../docs/perun-vs-rivals.md); [CHANGELOG.md](../CHANGELOG.md) | - |
| 15 | `review-lenses` Review lenses (scope as stated by the owner) | in flight | -, reliability | 0.62 | Open lens issues 1430 to 1433: 4 open today; each closed with a planted-defect eval. | owner:2026-10-16; issue:#1430; issue:#1431; issue:#1432; issue:#1433 | - |
| 16 | `loop-before-after-measure` Measure the improvement loop against a plain 'what should we build next' prompt on two real repos | open | CPO, learning | 0.60 | Win rate vs a plain prompt on a rubric-free judge: unmeasured now; 20 or more pairs; claim a win only if the lower bound is above 0.5. | [improvement-loop.md](../.claude/skills/agentic-ceo/references/improvement-loop.md); [perun-vs-rivals.md#h3-skill-routing-age…](../docs/perun-vs-rivals.md#h3-skill-routing-agentic-ceo-pack-30-prompts-n1-per-prompt); [bench](../docs/bench) | owner: paid bench |
| 17 | `judge-independence-rerun` Re-run the rubric-free comparisons with a judge from another vendor family | open | CPO, learning | 0.38 | Re-tested pairs judged by a different-vendor judge: 0 of 5 now, 5 of 5; per pair, whether the outcome moved by more than its interval. | [perun-vs-rivals.md#what-was-not-measured](../docs/perun-vs-rivals.md#what-was-not-measured); [perun-vs-rivals.md#h1d-idea-critic-prod…](../docs/perun-vs-rivals.md#h1d-idea-critic-product-discovery-and-growth-analytics-re-tests-rubric-free-blind-judge-2026-10-16-425-of-a-6-cap-preregistered-in-docsbenchskill-rubricfree-1016) | owner: paid calls and a second vendor's key |
| 18 | `url-switch` URL switch to protocol/perun and the plugin rename | in flight | -, polish | 0.31 | Lines naming the previous repository URL in tracked files outside CHANGELOG.md: 23 in 14 files (git grep at c097d01f) to 0 outside fixtures and tests that name it on purpose; plugin name still deep-code-review in .claude-plugin/plugin.json. | [README.md](../README.md); [plugin.json](../.claude-plugin/plugin.json); [perun_auto_update.py](../.claude/skills/agentic-delivery/scripts/perun_auto_update.py); owner:2026-10-16 | - |
| 19 | `distribution-listing` Distribution: an official marketplace listing and positioning against competing prose skills (issue 273) | open | CMO, growth | 0.27 | Verified marketplace listings: 0 of 1 now (status unverified, section 3), 1 of 1; no usage target, since installs are not countable. | issue:#273; [perun-vs-rivals.md#3-what-the-rivals-ha…](../docs/perun-vs-rivals.md#3-what-the-rivals-have-that-perun-lacks); [perun-vs-rivals.md#h10-install-and-upda…](../docs/perun-vs-rivals.md#h10-install-and-update-15830-timings-measured-on-15820-host-and-uninstall-fixes-from-the-15830-release-checks) | owner: a marketplace submission is an external send |
| 20 | `real-host-smoke-tests` Smoke-test more of the listed hosts on real hosts, starting with the ones that cost nothing to run | open | CTO, reliability | 0.25 | Hosts smoke-tested on a real host (11 of 11 skills listed): 1 of 19 now, 5 of 19. | [perun-vs-rivals.md#h10-install-and-upda…](../docs/perun-vs-rivals.md#h10-install-and-update-15830-timings-measured-on-15820-host-and-uninstall-fixes-from-the-15830-release-checks); [host-safety.md](../docs/host-safety.md); [CHANGELOG.md](../CHANGELOG.md) | owner: vendor accounts or CLIs for each host |
| 21 | `peer-survey-v2` Peer survey v2: per-item counts, a very-disappointed question and a week-4 still-using question | open | CPO, learning | 0.23 | Open items with a sourced (not assumed) reach: 0 now, at least half at the next run; product-market-fit read: UNVERIFIED now, a very-disappointed share with n stated. | survey:2026-10-16; [SKILL.md](../.claude/skills/product-discovery/SKILL.md); [perun-vs-rivals.md#3-what-the-rivals-ha…](../docs/perun-vs-rivals.md#3-what-the-rivals-have-that-perun-lacks) | owner: sending the form is an external send |
| 22 | `product-skill-runnable-checks` Give each product skill one runnable check or template, as the rivals ship | open | CPO, growth | 0.05 | Product skills with a runnable script: 0 of 5 now (product-discovery, growth-analytics, positioning, business-ops, product-output-safety); 2 of 5 only if the differentiator bench shows a tooling gap. | [perun-vs-rivals.md#3-what-the-rivals-ha…](../docs/perun-vs-rivals.md#3-what-the-rivals-have-that-perun-lacks); [perun-vs-rivals.md#h1d-idea-critic-prod…](../docs/perun-vs-rivals.md#h1d-idea-critic-product-discovery-and-growth-analytics-re-tests-rubric-free-blind-judge-2026-10-16-425-of-a-6-cap-preregistered-in-docsbenchskill-rubricfree-1016) | - |

Score inputs:

| # | reach | impact | confidence | effort (typed + gates + wait) | stage × | vision × | score | assumed (R reach, I impact, E effort) |
|---|---|---|---|---|---|---|---|---|
| 1 | 3 | 2 | 1 | 2 | 1.25 | 1 | 3.75 | E |
| 2 | 3 | 3 | 1 | 3 | 1.25 | 1 | 3.75 | E |
| 3 | 4 | 2 | 1 | 3 | 1.25 | 1 | 3.33 | E |
| 4 | 3 | 1 | 0.5 | 1 | 1.25 | 1 | 1.88 | I E |
| 5 | 3 | 2 | 0.5 | 3 | 1.25 | 1 | 1.25 | I E |
| 6 | 5 | 2 | 0.5 | 3 | 0.75 | 1 | 1.25 | I E |
| 7 | 3 | 1 | 0.5 | 2 | 1.25 | 1 | 0.94 | I E |
| 8 | 3 | 1 | 0.5 | 2 | 1.25 | 1 | 0.94 | I E |
| 9 | 2 | 2 | 0.5 | 3 | 1.25 | 1 | 0.83 | I E |
| 10 | 4 | 1 | 0.5 | 2 | 0.75 | 1 | 0.75 | R I E |
| 11 | 2 | 2 | 0.5 | 2 + 2 + 0 = 4 | 1.5 | 1 | 0.75 | R I E |
| 12 | 5 | 2 | 0.5 | 4 + 2 + 0 = 6 | 0.75 | 1 | 0.62 | R E |
| 13 | 2 | 1 | 0.5 | 2 | 1.25 | 1 | 0.62 | R I E |
| 14 | 3 | 1 | 0.5 | 3 | 1.25 | 1 | 0.62 | R I E |
| 15 | 3 | 1 | 0.5 | 3 | 1.25 | 1 | 0.62 | R I E |
| 16 | 2 | 2 | 0.5 | 3 + 2 + 0 = 5 | 1.5 | 1 | 0.60 | R I E |
| 17 | 2 | 1 | 0.5 | 2 + 2 + 0 = 4 | 1.5 | 1 | 0.38 | R I E |
| 18 | 5 | 1 | 0.5 | 2 | 0.5 | 0.5 | 0.31 | I E |
| 19 | 5 | 3 | 0.5 | 5 + 2 + 0 = 7 | 0.5 | 0.5 | 0.27 | R I E |
| 20 | 2 | 1 | 0.5 | 3 + 2 + 0 = 5 | 1.25 | 1 | 0.25 | R I E |
| 21 | 1 | 2 | 0.5 | 1 + 2 + 3.5 = 6.5 | 1.5 | 1 | 0.23 | R I E |
| 22 | 2 | 1 | 0.5 | 5 | 0.5 | 0.5 | 0.05 | R I E |

### Top 3 open items attacked by idea-critic

- 1. `autonomy-advisor`: **PASS_TO_USER** (inline). Strongest attack survived: It may duplicate the in-flight sandbox preflight, and sandbox_probe.py already prints a fix per failure. It survives as a separate item only because it targets the permission rules for the 4 named tools (gh, Chromium, Postgres, tsx IPC) that sandbox_probe.py does not probe, and the first kill criterion closes it if the preflight lane covers them. Kill criteria: The preflight lane already prints fix rules: close as a duplicate; A printed rule widens access beyond the failing tool in any test: stop Remaining risk: Overlap with the in-flight preflight is unverified because that lane has no open PR.
- 2. `handback-automator`: **PASS_TO_USER** (inline). Strongest attack survived: Fast-forwarding the base branch and posting to a tracker are shared-state actions, so automating them could remove the human gate. It survives because the default is dry run, push and merge still need the owner's grant as today, and cleanup is printed, never run. Kill criteria: The composer has to reimplement any gate logic: stop and call the existing scripts only; A fast-forward runs without a human push grant in any test: stop and ship dry-run only Remaining risk: A second entry point to keep in step with lane-preamble.md.
- 3. `background-work-guard`: **PASS_TO_USER** (inline). Strongest attack survived: A guard that blocks on any cwd process will hold lanes behind long-lived dev servers the user owns. It survives because the existing wait bound releases the hold, the check fails open when it cannot see, and the kill criterion drops it to advisory after 1 false block per 20. Kill criteria: More than 1 false block per 20 handbacks in the first 2 weeks: ship advisory only; ps or lsof unavailable on a host: fail open with COULD_NOT_CHECK, never block Remaining risk: A second class of processes the cwd check cannot see.

Dedup check: 28 items, near-duplicate titles (similarity 0.85 or more): none.

## 4. Technical-direction decisions (ADRs)

### ADR-1: Keep the flake ledger per host and untracked (pipeline), serves `flake-ledger-quarantine`

- Status: proposed
- Context: train_flake.sh decides REAL or FLAKE per run with a same-host baseline file whose header it checks (a baseline from another host is refused), and it keeps no per-test history beyond that baseline. preflight.py already keeps a per-repo timing cache file meant to be gitignored (.preflight-times.json), so a per-host untracked store has precedent, and flakiness depends on the host.
- Options: (A) **Per-host untracked ledger beside the baseline**: Cheap, no merge conflicts, matches the same-host rule; each host learns its flakes separately. (B) **Committed ledger file**: Shared across hosts and visible in review; conflicts on every train and records one host's flakes as facts. (C) **Do nothing**: No new state; every run re-triages the same tests and keeps dropping PRs.
- Decision: We will keep the ledger per host and untracked, and print its quarantine list in the train summary, because train_flake.sh already refuses a baseline from another host and a committed file would conflict on every train.
- Consequences: Good: no shared state and no conflicts. Bad: each host re-learns flakes, and a quarantined test hides a real regression until its entry expires. Neutral: promotion to a committed skip list goes through an ordinary PR.
- Reversal cost: Low, a two-way door: delete the file and the summary line; no other tool reads the format.

### ADR-2: Compose the existing handback scripts in one thin entry point (tooling), serves `handback-automator`

- Status: proposed
- Context: A handback is six manual steps today (lane-preamble.md): wait, handback, clean_finished.sh, reap_own.sh, the changelog fragment and git diff --check. Each step already has a script and tests.
- Options: (A) **A thin script that calls the existing scripts in order and prints the cleanup**: No duplicated logic; one more entry point to keep in step with lane-preamble.md. (B) **Grow lane_guard.py handback**: One entry point; mixes the start-of-lane guard and the end-of-lane automation in one file. (C) **Do nothing, prose only**: No code; the survey (P7) still asks for automation.
- Decision: We will add a thin composer that calls the existing scripts and prints, never runs, the worktree cleanup and any base-branch fast-forward not covered by a human push grant, because every step already has a tested script and shared-state actions keep their human gate.
- Consequences: Good: fewer steps with no new gate logic. Bad: a second entry point to maintain. Neutral: dry run is the default, so the first release automates less than the survey asked for.
- Reversal cost: Low: delete one file and its preamble line.

### ADR-3: Enforce the background-work rule at the SubagentStop hook (architecture), serves `background-work-guard`

- Status: proposed
- Context: lane-preamble.md says never end a turn with background jobs running, and the survey (P4) says lanes still do. handback_cap.py already blocks a handback while a git push from the worktree is live, by matching PUSH_RE against the process list and checking the cwd with lsof, but it matches nothing else.
- Options: (A) **Extend handback_cap.py's process check to any process with its cwd in the worktree**: Reuses a tested mechanism with its bounded wait and fail-open path; may hold a handback on a long-lived dev server. (B) **Keep the rule in prose**: No code; it has not held (survey P4). (C) **Register every background launch in a wrapper**: Exact, but needs a harness feature and touches every lane.
- Decision: We will extend the existing check to any process whose cwd is inside the worktree, with the same wait bound and the same COULD_NOT_CHECK fail-open path, because the hook already runs at the right moment and holds the cwd logic.
- Consequences: Good: closes the gap where the push check is already enforced. Bad: a user-owned dev server inside the worktree can hold a handback until the bound expires. Neutral: the nested-worktree bug in issue 1530 must be fixed first or together.
- Reversal cost: Low: revert one function; no data or format is involved.

### ADR-4: Store survey counts as an aggregate CSV in the repo (tooling), serves `peer-survey-v2`

- Status: proposed
- Context: roadmap_rank.py reads each input's source as a path, a link or the word assumed, so measured reach needs a stable file that carries no personal data.
- Options: (A) **Aggregate CSV under docs/, counts and n only**: Versioned with the roadmap, reproducible and checkable by the privacy gate; no raw answers are kept. (B) **Counts in an issue comment**: Easy to post; not versioned with the roadmap and lost if the tracker changes. (C) **A form tool's dashboard**: Zero setup; third-party data that cannot be cited or re-derived from the repo.
- Decision: We will commit an aggregate CSV of counts and n only under docs/ and cite it from reach_src, because that keeps the roadmap reproducible and carries no names.
- Consequences: Good: measured reach is checkable in review. Bad: raw answers are not kept, so a question cannot be re-sliced later. Neutral: the form itself stays outside the repo.
- Reversal cost: Low: the CSV is data; delete it and reach goes back to assumed.


## 5. Tracker-ready issues

Open items only (in-flight work already has its issue). Priority is rank-derived among open items (ranks 1-3 P1, 4-6 P2, the rest P3); P0 is a human call and is never assigned here. Issues are drafted for P1 and P2 only; a P3 item stays in the table until it is promoted.

### P1: Autonomy advisor: read the sandbox and permission settings and print the narrow rules that stop sandbox retries, never writing settings

- Labels: `reliability`, `COO`, `stage:mvp`
- Where: .claude/skills/agentic-delivery/scripts/sandbox_probe.py and the operating-layer settings template.
- Done when: Run in a Claude Code Bash call, it probes gh, Chromium, Postgres and tsx IPC, and for each failure prints the one narrow permission or exclude rule that clears it; it writes nothing and exits non-zero while a failure remains.
- Verify: On a scratch host, apply each printed rule and re-run the advisor: the failure clears, and no printed rule allows more than its failing tool.
- Why: Delivery: about 5 sandbox-blocked retries per session (F2) cost autonomy, and the owner wants safety defaults that keep agents working without hand-edited settings. (vision: aligned)
- Success metric: Sandbox-blocked retries per session: about 5 (field report F2) to 1 or fewer; one printed rule per probed failure, 0 settings files written.
- Evidence: [peer-survey-2026-10-16.md#f2](../docs/peer-survey-2026-10-16.md#f2); [peer-survey-2026-10-16.md#p3](../docs/peer-survey-2026-10-16.md#p3); [sandbox_probe.py](../.claude/skills/agentic-delivery/scripts/sandbox_probe.py); [host-safety.md](../docs/host-safety.md)
- Risks: Advice for a tool that was not probed is a guess: print rules only for probed failures, never write settings (the owner adds the rule), and keep each rule as narrow as the failing tool.
- Merged from: COO lens: field report F2; CISO lens: narrow rules, not blanket allows
- Score: 3.33 = 4 × 2 × 1 ÷ 3 × 1.25 × 1 (open rank 1 of 15); assumed: effort

### P1: Lane-handback automator: gates, required-check names, base-branch fast-forward and tracker post; cleanup printed, never run

- Labels: `velocity`, `COO`, `stage:mvp`
- Where: .claude/skills/agentic-delivery/scripts/lane_guard.py (handback), clean_finished.sh, reap_own.sh and templates/lane-preamble.md.
- Done when: One command runs the gates, prints the required check names for the sha, fast-forwards the base branch only under a human push grant (default: dry run), posts the tracker update, and prints, never runs, the worktree cleanup; a red gate exits non-zero and names the gate.
- Verify: A fixture lane in the style of scripts/test-delivery-friction.sh with a green run and a red run; a grep proves the script contains no 'git worktree remove'; lane_guard.py handback still passes unchanged.
- Why: Delivery: the handback is the last mile of every lane and the survey (P7) asks for it to be automated. (vision: aligned)
- Success metric: Manual steps per handback: 6 (lane-preamble.md: wait, handback, clean_finished.sh, reap_own.sh, changelog fragment, git diff --check) to 1; handbacks needing a second pass: unmeasured, count for 2 weeks.
- Evidence: survey:2026-10-16#P7; [lane-preamble.md](../.claude/skills/agentic-delivery/templates/lane-preamble.md); issue:#1530; issue:#1531
- Risks: Fast-forwarding the base branch and posting to a tracker are shared-state actions: dry-run by default, the human push grant stays, and cleanup is printed, never run.
- Merged from: COO lens: survey P7; CTO lens: teardown standard (issue 1531) is the handback's tail; CISO lens: shared-state actions keep the human gate
- Score: 1.25 = 3 × 2 × 0.5 ÷ 3 × 1.25 × 1 (open rank 2 of 15); assumed: impact effort

### P1: Block a handback while any background test or build from the worktree is still running

- Labels: `reliability`, `COO`, `stage:mvp`
- Where: .claude/skills/agentic-delivery/scripts/handback_cap.py (the SubagentStop hook; its process check matches git push only).
- Done when: The hook blocks while any process whose cwd is inside the worktree is alive, not only git push, bounded by the existing wait limit; when ps or lsof cannot answer it still fails open with COULD_NOT_CHECK; the nested-worktree case from issue 1530 is covered.
- Verify: python3 .claude/skills/agentic-delivery/scripts/handback_cap.py --selftest with a live sleep-process fixture and a nested-worktree fixture.
- Why: Delivery: the rule exists in prose (lane-preamble.md) and the survey shows it does not hold; enforce it where the push check already lives. (vision: aligned)
- Success metric: Lanes handing back with a live background process: unmeasured now (survey P4), target 0; the guard blocks the planted fixture 1 of 1.
- Evidence: survey:2026-10-16#P4; [handback_cap.py](../.claude/skills/agentic-delivery/scripts/handback_cap.py); [lane-preamble.md](../.claude/skills/agentic-delivery/templates/lane-preamble.md); issue:#1530
- Risks: False blocks on long-lived dev servers the user owns: scope the check to the worktree and keep the release valve.
- Merged from: COO lens: survey P4; CTO lens: handback_cap.py matches git push only (PUSH_RE)
- Score: 0.94 = 3 × 1 × 0.5 ÷ 2 × 1.25 × 1 (open rank 3 of 15); assumed: impact effort

### P2: Land the worktree janitor (PR 1382, open since 2026-10-07) and the teardown standard (issue 1531)

- Labels: `reliability`, `COO`, `stage:mvp`
- Where: PR 1382 (janitor), the teardown standard in issue 1531, .claude/skills/agentic-delivery/scripts/clean_finished.sh and reap_own.sh.
- Done when: The standard (exact-PID teardown, EXIT traps, atomic claims) is written and the janitor follows it: it reports and prints cleanup commands first and removes only what it proves it owns; PR 1382 is merged or closed.
- Verify: A fixture with one owned and one foreign worktree plus a foreign dev server: the janitor removes or prints only the owned one and never signals the foreign process; session_brief.py reports 0 finished worktrees afterwards.
- Why: Delivery: stale worktrees and orphan dev servers are the cleanup cost of every fleet run, and the platform now guards hook-made worktree removal too (Claude Code 2.1.301), so Perun's own handling should not be weaker. (vision: aligned)
- Success metric: Finished worktrees and leftover dev servers at session start: 130 or more in the field report behind session_brief.py, target 0 after a train; PR 1382 age 9 days to merged or closed.
- Evidence: pr:#1382; issue:#1531; [session_brief.py](../.claude/skills/agentic-delivery/scripts/session_brief.py); https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md
- Risks: A janitor that deletes is itself a host-safety risk: report and print before it removes, and never act on a path it did not create.
- Merged from: COO lens: stale worktrees (session_brief.py); CISO lens: a deleting janitor is a host-safety risk
- Score: 0.94 = 3 × 1 × 0.5 ÷ 2 × 1.25 × 1 (open rank 4 of 15); assumed: impact effort

### P2: Per-test flake ledger with quarantine, so flaky tests stop dropping PRs from trains

- Labels: `reliability`, `COO`, `stage:mvp`
- Where: .claude/skills/agentic-delivery/scripts/train_flake.sh and merge_train.py (ledger and train summary).
- Done when: Each isolated re-run outcome is recorded per test; a test over the flake threshold is quarantined, reported in the train summary and not blamed on a PR, until its entry expires; the 1.584.0 false-blame rate does not regress.
- Verify: bash scripts/test-train-flake-rate.sh still passes; a new ledger test; replay the H11 fixture in docs/bench/merge-train-1584 and compare PRs landed (4 of 6 today).
- Why: Delivery: the 1.584.0 train cut false blame to 3.1 percent in simulation (24.8 percent before) but a regression that is also flaky on the base still lands 70 percent of the time (210 of 300, H11); a ledger is the next lever. (vision: aligned)
- Success metric: PRs parked as flake-blamed per 100 train PRs: unmeasured now (survey P5), measure for 2 weeks then target 1 or fewer; tests with 2 or more intermittent failures listed in a ledger: 0 now.
- Evidence: survey:2026-10-16#P5; [perun-vs-rivals.md#h11-merge-train-15840](../docs/perun-vs-rivals.md#h11-merge-train-15840); [train_flake.sh](../.claude/skills/agentic-delivery/scripts/train_flake.sh)
- Risks: Quarantine can hide a real regression: keep the base-baseline rule and expire entries.
- Merged from: COO lens: survey P5; CTO lens: the residual cost in H11
- Score: 0.83 = 2 × 2 × 0.5 ÷ 3 × 1.25 × 1 (open rank 5 of 15); assumed: impact effort

### P2: Zero-chat lanes: a lane's chat is one status line, everything else goes to files

- Labels: `cost`, `CFO`, `stage:mvp`
- Where: .claude/skills/agentic-delivery/scripts/handback_cap.py, subagent_start_inject.py and templates/lane-preamble.md.
- Done when: A baseline of chat tokens per lane is measured, then the lane brief and hook keep mid-run chat to status-only lines and the measured drop is reported.
- Verify: python3 .claude/skills/agentic-ceo/scripts/token_report.py before and after on the same lane type; the drop is stated with n.
- Why: Token optimisation: lane tokens should go to work, not narration; the final message is already capped, mid-run chat is not. (vision: aligned)
- Success metric: Chat tokens per lane run: unmeasured (F3 supplies none); measure with token_report.py first, then target half; final message already capped to 1 line by handback_cap.py.
- Evidence: [peer-survey-2026-10-16.md#f3](../docs/peer-survey-2026-10-16.md#f3); [handback_cap.py](../.claude/skills/agentic-delivery/scripts/handback_cap.py); [lane-preamble.md](../.claude/skills/agentic-delivery/templates/lane-preamble.md)
- Risks: Suppressing mid-run notes can hide a stuck lane: keep the progress file that lane_guard.py wait writes.
- Merged from: CFO lens: token spend; COO lens: lane hygiene
- Score: 0.75 = 4 × 1 × 0.5 ÷ 2 × 0.75 × 1 (open rank 6 of 15); assumed: reach impact effort

P3, no issue drafted until promoted: `differentiator-bench`, `review-cost-per-recall`, `derived-numbers-gate`, `loop-before-after-measure`, `judge-independence-rerun`, `distribution-listing`, `real-host-smoke-tests`, `peer-survey-v2`, `product-skill-runnable-checks`.

_Generated by `roadmap_rank.py` from the input JSON: edit the input and re-run, never this text._
<!-- roadmap:end -->

---

# Agent suite roadmap (proposed / living)

> **Status:** a design captured so nothing is lost — **proposed**, pending the
> owner decisions flagged in *Decisions for the owner*. Nothing here is built
> except items marked ✅. The `deep-code-review` **skill name stays stable**
> regardless of any repository/umbrella rename. Dated 2026-09-11.

## BLUF
This repository is evolving from a **portable code-review bar** into a
**stage-aware agentic product-building suite**: a "CEO" orchestrator plus opt-in
specialist skills that support a solo or small builder across a product's whole
life — code, infrastructure, docs, product/PMF, prioritization, discovery,
growth, positioning, and business/ops — while **preventing over-engineering** and
**never fabricating**. One epistemic spine holds every skill together. Navigation
is by **lenses over ~10 skills**, not a sprawl of new ones. Build the spine and the
lowest-risk skills first; add the advisory skills, on the tightest leash, last.

## The epistemic spine (non-negotiable in every skill) — and the differentiator
1. **Frameworks + the user's own inputs + observable evidence.** Apply named
   industry frameworks to the builder's actual context; never invent
   market/financial/competitor facts.
2. **Route the unknowable.** When correctness depends on context the repo/agent
   does not hold (a market number, a legal/tax/securities question), hand it to
   real research or a licensed professional — never conclude on it.
3. **Stage-aware.** Calibrate what to do *and what not to do* to lifecycle stage;
   the floor (security, secrets, auth, data-loss/backups) never relaxes.
4. **Surface uncertainty; skip rather than guess.** Empty beats fabricated.

The market has converged on "AI cofounder / agent team" persona products;
research found their **limits language is near-empty**. So the differentiator is
not more personas — it is **honesty, verification, and stage-awareness**. That is
the white space, and it is exactly this repo's existing thesis.

## Architecture — lenses over ~10 skills (not 70)
A naive `STAGE × AREA` grid invites one skill per cell and detonates the repo's
anti-duplication thesis. Instead, following the pattern `deep-code-review` already
runs (fixed domains + an `archetype → load map` + a role overlay that "never adds
or drops a domain"):

- **Keep ~10 skills; admit a new one only by the admission rule.** A new *skill* is
  justified only when it **cannot** be a lens or reference over an existing skill,
  **or** when a safety boundary requires its own home (the reason the suite is 10, not
  8 — `business-ops` keeps the call on your numbers separate from routing the binding part to a professional).
  Lenses and references are **not** skill rows; do not count them as such. `STAGE` and
  `AREA` are **lenses** that select and order existing content. The orchestrator routes
  `(stage, area) → (skill, lens)`.
- **Navigation, two layers.** *Passive:* each skill's frontmatter `description` is
  the routing key — disjoint "use when…", one home per skill, no duplication
  (Level-1 metadata is ~100 tokens/skill, so the orchestrator can hold the whole
  map and still route precisely). *Active:* the CEO reads `(stage + need +
  artifact)` and dispatches.
- **The suite map is a registry, not a bundle.** It *describes how to reach* each
  skill; it never holds copies. One index serves agents and humans alike.
- **Topology by work type.** Fan out (3–5 subagents, clear boundaries) only for
  read-mostly, decomposable work (research, audit, review); keep **writing
  single-writer**. Size effort to the project — a small/early project is one agent
  wearing several skill-hats, not a swarm burning tokens.

## Stage model (shared) — ✅ shipped
`prototype → mvp → growth → mature`, calibrating *demands* (urgency), never a
defect's intrinsic severity, and never the floor. Lives in `deep-code-review`
(the first-response `STAGE` field + the *Project stage* section + the going-forward
roadmap). Every advisory skill keys to it.

## The suite (skills and lenses)
| Skill | Status | Role |
|---|---|---|
| `deep-code-review` | ✅ (stage-aware) | The review bar; archetype/role/stage lenses; parallel-audit fan-out |
| `agentic-delivery` | ✅ | Gated G0–G10 build; roles as hats; one writer per worktree |
| `idea-critic` | ✅ | Pre-owner adversarial attack (the critic half of "critic + verifier") |
| `communication-structure` | ✅ | BLUF, one-ask human-facing messages |
| `contribution` | ✅ (hardened — PR #26) | Human-gated, privacy-safe upstream self-improvement |
| agent-readiness lens | ✅ | Is the repo agent-ready? (a `role-coverage.md` lens) |
| `agentic-ceo` (orchestrator) | ✅ vendored (1.37.0) | Suite registry + (stage, area) → (skill, lens) routing + effort-sizing + chaos playbook; defers general delivery/critique to `agentic-delivery` / `idea-critic` |
| `infra-evolution-by-stage` (ref) | ✅ shipped 1.35.0 (#28→#51) | When to add CI/staging/observability/k8s — extends the going-forward roadmap |
| `docs-evolution-by-stage` (ref) | ✅ shipped 1.35.0 (#29→#51) | Which docs at which stage; docs acquire normative force as the product matures |
| discovery / validation | ✅ shipped in `product-discovery` (1.36.0) | Design + interpret real user research; never fabricate findings |
| prioritization / focus | ✅ shipped in `product-discovery` (1.36.0) | Riskiest-assumption gate; what to build now vs. defer |
| product-strategy / PMF | ✅ folded into `product-discovery` (1.39.0) — PMF read + Non-goals lens; standalone skill dropped per carve | JTBD, PMF signals, what *not* to build |
| growth / analytics | ✅ shipped in `growth-analytics` (1.38.0) | Retention-first; North Star; what to instrument per stage |
| positioning / branding | ✅ shipped in `positioning` (1.41.0) | VPC → positioning → message house, as a hypothesis; thin guide; never fabricates TAM/competitor/quotes/clearance |
| business / ops | ✅ shipped in `business-ops` (1.42.0) | leads with the call on pricing/unit-economics numbers; routes the binding legal/tax/securities part to a professional; thin guide |
| CEO-under-pressure | Researched → `agentic-ceo` (#36) | Capture losslessly → reflect back → triage → one next action → tracked backlog → support by action (never "calm down") |
| responsible-AI / output safety | Researched → **build first among gaps** (NEW skill) | Govern the harm the product's own outputs do to end-users (NIST AI RMF lens) |
| further areas (gap-analysis) | Researched → *Further areas* + issues | regulated-triage, support-ops, op-readiness, privacy-by-design, decision-hygiene, billing — mostly lenses |

## Build order (research-backed)
1. **Critic + verifier** — ✅ have (`idea-critic`, `deep-code-review`); *assemble*, don't rebuild.
2. **Discovery + PMF-gate** — the top risk-reducer: a coding agent now builds the *wrong thing* faster, so the seat it does not fill (is this worth building?) is the highest leverage. New.
3. **Product-strategy / "what NOT to build"** — governs the coding agent's backlog; prevents gold-plating.
4. **Analytics scoreboard + one primary metric** — tells the builder whether the fast-built thing works; anchors every skill to one axis.
5. **Stage-aware CEO spine** — extend `agentic-ceo` with stage/size-aware routing + the suite registry.
- **Shipped (1.35.0):** the `infra-evolution-by-stage` and `docs-evolution-by-stage` references (extend the going-forward roadmap).
- **Defer / lightest touch:** engineering advisor (already covered by the coding agent), design/UX (partly covered + `product-ux-quality`), legal/ops (one-time checklists + a tripwire), fundraising/hiring (stage-gated), positioning/branding + business/ops (highest fabrication-risk → thin "framework + the questions you must answer" guides, built last).

**Sequencing rationale (and the pushback that produced it):** do **not** big-bang a
dozen skills — that is the exact over-engineering the suite exists to prevent, and
it front-loads the riskiest (business/branding) skills before the pattern is
proven. Build the spine + the lowest-fabrication-risk skills first, prove
navigation end-to-end, then add the advisory skills with the tightest leash.

## Per-area boundaries (frameworks by name; the hard line for each)
- **Discovery/validation:** Mom Test, JTBD switch interviews, Teresa Torres
  continuous discovery, assumption/riskiest-assumption mapping, fake-door/concierge
  tests. *Boundary:* design and interpret research the **user runs**; never
  fabricate quotes, personas, market size, or a "validated" verdict; refuse to emit
  an "example finding" (it becomes fake evidence).
- **Product/PMF/prioritization:** riskiest-assumption gate (name it, run the
  cheapest test *before* building — it produces a refusal); PMF read via the
  "very-disappointed" survey + a flattening retention cohort; ICE over RICE for a
  solo builder. *Boundary:* the skill owns the question, structure, and arithmetic;
  it **routes for every input** and never emits a scoring table with invented
  numbers.
- **Growth/analytics:** retention-first (AARRR read bottom-up), a customer-value
  North Star (not vanity metrics), instrument only what answers a named question.
  *Boundary:* no fabricated benchmarks; route real figures to the user's analytics.
  Note: the product-analytics identifier rule *inverts* the ops-observability one
  (a stable per-user id is required for cohorts) — a seam to state, not restate.
- **Positioning/branding:** Value Proposition Canvas → positioning → a message
  house → validation with real buyers; a "minimum viable brand" pre-PMF. *Boundary:*
  frameworks yield a **hypothesis**; the evidence comes from outside the model.
  Never fabricate TAM, competitor claims, quotes, outcomes, or trademark/domain
  clearance. Premature branding/scaling is a documented failure mode.
- **Infra-evolution-by-stage:** infrastructure is *earned*, not provisioned — start
  with one boring, well-modularized deployable; add each layer (CI, staging, IaC,
  observability, containers, orchestration, service extraction) only on a concrete
  observable trigger. *Boundary:* the floor never relaxes; route the six
  business/ops unknowables (real SLA, regulatory class, revenue exposure, funding
  runway, team trajectory, customer concentration) to the owner. Complements
  `infra-iac-containers.md` (how-to-secure) with a when-to-add lens.
- **Docs-evolution-by-stage:** docs acquire **normative force** as the product
  matures — one-pager (persuade) → design-doc/RFC (decide) → spec (contract,
  CI-enforced); trigger, not calendar. Agent-legibility = a small always-loaded
  router + depth routed with "read this when…". Complements `docs-and-dx.md`.
- **Business/ops (asymmetric boundary):** *The call on your numbers* (pricing, unit
  economics): **apply** to the builder's own numbers with the formula and every
  assumption shown, flag thin data — but never turn arithmetic into a directive.
  *The binding, regulation-dependent part* (legal, tax, securities, employment
  classification, privacy compliance): **route to a licensed professional, never
  conclude**; fundraising (selling equity/SAFEs is a securities offering) *is* the
  boundary crossing. Standing disclaimer: educational information, not advice.

## The product ↔ user ↔ agent loop ("growing together")
Two nested build-measure-learn loops. **Loop 1** (the builder's product): the agent
structures feedback and proposes experiments; the human decides. **Loop 2** (the
suite's own improvement): capture each interaction → evaluate with a *split* rubric
(**deterministic gates** for the hard axes — boundary-compliance and
non-fabrication, because a fluent wrong answer fools an LLM judge; **LLM-judge, and
a decorrelated one, for the soft axes** only) → ratchet only through the
human-gated, generalization-checked `contribution` flow. Quality **only ratchets
up**: a regression gate stops backsliding, generalized eval cases raise the floor,
and a human authorizes every landing. The fuel is verified eval cases and
citations — not hoarded user data.

**Operational runbook:** [How Perun improves itself](self-improvement.md) makes this
loop executable — the concrete 8 steps, the tool each one uses, and the built-vs-planned
state of the split rubric.

## Additive principles (generalized from field practice and research)
- **Registry, not a bundle** — describe how to reach things; never duplicate them.
- **Store the query, not the answer; audit memory automatically** — a stored status
  rots silently; store how to re-derive it, and flag memories that stopped being true.
- **Issue contract: Where / Done-when / Verify / Why** — "Verify" is load-bearing;
  without it "done" is an opinion. Used for this repo's own backlog issues.
- **Unreadable must never look like empty** (= the repo's `UNVERIFIED`); **enforce
  rules in code, not prose** (= `contribution`'s `kernel-paths.txt` gate); **deny by
  default**. These validated recent work rather than changing it.

## CEO under pressure (chaos playbook) — folds into `agentic-ceo` (#36)
When the owner floods the orchestrator with many rapid, conflicting asks under real
pressure, the failure is to freelance (obey the last thing, drop the rest, act on
colliding orders) or to patronize ("calm down"). Support is **by action, not
affect** — six moves in order:
1. **Capture losslessly** — every request/aside becomes a numbered logged item
   before any judgement; tag request vs. context; nothing filtered or merged.
2. **Reflect the full list back** — the played-back numbered list *is* the
   acknowledgement; name any collision between items as its own finding.
3. **Triage to the vital few** — a sequential first-hit-wins chain: blocks-others or
   irreversible → Now; failing on the live surface → Now; time-critical but
   reversible → Next; else → Held (visible, not dropped).
4. **One highest-leverage next action** — the lead domino + a one-line why, offered
   as the existing A/B decision so the owner keeps final say.
5. **Hold the rest as a tracked backlog** — each item has a visible state (in-flight
   / next / held / dropped-with-reason); WIP-limit to one primary action.
6. **Support by action** — acknowledge the stakes as legitimate, show the list, name
   the move. **Forbidden:** "calm down"/"relax" (reactance + invalidation), toxic
   positivity, minimizing, narrating their feelings, "on it!" with nothing captured,
   silently absorbing conflicting orders.

Boundary: the agent is an **organizer, not a therapist** — the calm comes from the
system being visibly under control. Capture-mode is **not** yes-mode: it still
surfaces real disagreement (conflicts, quality-bar breaches, spread-thin mediocrity)
in one line with the standard cited, then the owner decides. Frameworks (by name):
GTD capture/clarify, incident command (single commander, unity-of-command, activity
log), emergency-severity triage, WIP limits, "the ONE thing," psychological
reactance, motivational-interviewing reflective listening.

## Further areas (from gap-analysis)
The suite is strong on builder + product + code; the gap is the **end-user runtime
axis** (what the product does to people once live) plus **operational readiness for
the bad day**. Mostly **lenses** over existing skills, not new skills. Ranked:
- **G1 · Responsible-AI / product-output safety** — NEW skill; govern harm from the
  product's own outputs (bias, hallucination-as-fact, missing AI-disclosure,
  deceptive patterns, unsafe automation). NIST AI RMF (GOVERN/MAP/MEASURE/MANAGE)
  lens; measure via the eval harness (domain J); human-in-the-loop on high-stakes
  outputs. **The defining hole for an agentic-*product* suite — build first.**
- **G2 · Regulated-domain obligation triage** — small lens; a design-time decision
  tree (health? payments? minors? EU data? biometrics? consequential decisions?)
  that names the regime and routes **before** architecture hardens; re-runs on
  entering a new market. Cheapest build, earliest bite; unblocks G4/G5.
- **G3 · Support & feedback operations** — lens; intake/triage/SLA + support→backlog.
- **G4 · Operational readiness** — lens over `agentic-delivery` postmortem + M/Q:
  incident-response runbook, severity + comms + status page, break-glass access,
  credential/renewal inventory with dead-man reminders, solo-founder succession.
- **G5 · Privacy/compliance by design (product artifacts)** — lens over Q: data
  inventory/ROPA, DPIA scaffold, consent-UX spec, subprocessor list; coupled to G2.
- **G6 · Decision hygiene for the builder's own calls** — a routed reference
  **extending `idea-critic`** (one-/two-way doors, base rates, kill criteria set up
  front) — not a new skill.
- **G7 · Billing / monetization system correctness** — a routed `deep-code-review`
  reference (metering, proration, dunning, tax, webhook idempotency, double-charge
  races) — mechanics of E/F/G/I applied to revenue.
- **Conditional:** G8 trust & safety / abuse (multi-user products), G9 vendor
  business-risk, G10 accessibility-as-design (mostly redundant with domain P).
- **Do NOT build (redundant):** cost / i18n / a11y-code-gate / supply-chain /
  data-integrity — already covered. **Owned by planned skills (name in their
  charters):** scope-defense → prioritization; data-as-moat → product-strategy;
  event-taxonomy → growth; pricing-strategy → business-ops; cloud right-sizing →
  infra-by-stage.
- **Boundary (all gaps):** inventory / scaffold / checklist / red-team / cite-only-
  what-was-fetched; **never** fabricate a statute, deadline, CWE, or metric; route
  every legal/regime determination to a licensed professional. Legal specifics stay
  **by-name / UNVERIFIED** until fetched (as `privacy-compliance.md` already does).
  The NIST AI RMF core function names (Govern/Map/Measure/Manage) are confirmed
  (`docs/standards-index.md`); its AI RMF 1.0 / Generative AI Profile control
  specifics and GDPR/DPIA/COPPA/PCI/breach-clock specifics were not — fetch before
  citing.
- **Build first among gaps:** G1, then G2 (unblocks G4/G5), then G3.

## Decisions for the owner (open)
1. **Rename / umbrella.** Defensible now that scope has widened (candidate: a
   Slavic-mythology theme, e.g. a "Perun" orchestrator, as a *thin* identity layer
   over functional skill names). Keep the `deep-code-review` skill name. Execute
   only after the spine is proven; owner picks the name; a migration checklist ships
   with it. GitHub auto-redirects the old repo URL, so the blast is mostly README /
   marketplace slug / `plugin.json` name.
2. **`agentic-ceo`:** ✅ **resolved — vendored into this repo** (1.37.0, the suite
   conductor). Chosen over reference-global so the suite stays portable; coexists
   with any global skill of that name via project-scoping.
3. **Business-advisory skills:** full "advisor" skills, or thin "framework + the
   questions you must answer yourself" guides? (Recommendation: thin guides — lowest
   fabrication surface.)
4. **Suite scale (#66):** ✅ **resolved — keep ~10 under a written admission rule**
   (Architecture §). A new *skill* must fail the "can this be a lens/reference over an
   existing skill?" test **or** be a safety boundary; otherwise it lands as a lens/ref,
   and lenses/refs are not counted as skill rows. Applying it to the gap backlog:
   **#43–#49 are lenses/references** over existing skills; only **#42
   (product-output-safety / responsible-AI)** is admitted as standalone **skill #11** —
   output-harm governance is a distinct method from code-security and is a safety
   boundary. Residual risk: if #42 drafts thin, fold it as a `deep-code-review` lens
   rather than ship a standalone skill.

## Status ledger (2026-09-11)
- **Suite complete + hardening — main @ 1.48.0 as of this snapshot (current release: see `.claude/skills/deep-code-review/VERSION` / `CHANGELOG.md`), 11 skills.** Shipped: contribution overlay
  (1.31.0) · agent-readiness lens (1.32.0) · stage-aware review + going-forward roadmap
  (1.33.0) · contribution hardening (1.34.0; contribution 1.1.0) · infra/docs
  stage-evolution refs (1.35.0) · `product-discovery` (1.36.0, +Non-goals 1.39.0 →
  1.1.0) · `agentic-ceo` conductor (1.37.0, +full registry 1.43.0 → 1.1.0) ·
  `growth-analytics` (1.38.0) · `positioning` (1.41.0) · `business-ops` (1.42.0) ·
  no-slop output contract (`communication-structure` → 1.2.0, at 1.40.0). Each new
  skill passed an independent reviewer pass before merge.
- **Post-build hardening (1.44–1.47):** suite-enumeration gate (1.44.0, #62) · DCR
  fabrication-refusal eval (1.45.0, #65) · `--recommend` surfaces advisory overlays
  (1.46.0, #68) · README "which skill when" quickstart (#67) · offline eval-predicate
  discrimination gate (1.47.0, #61 slice 1) · growth-analytics benchmark binding (offline net) ·
  **product-output-safety = skill #11** (1.48.0, #42 — the one gap admitted standalone under the #66 rule).
- **Owner decisions:** #39 (agentic-ceo) **resolved — vendored**; #40 (business-advisory
  shape) **resolved — thin guides**; #38 (rename) **deferred** until the suite is proven.
- **Post-build backlog (filed):** #61 live eval harness · #62 suite-enumeration gate ·
  #63 routing eval coverage · #64 eval-id anti-drift gate · #65 DCR fabrication eval ·
  #66 [decision] suite scale — ✅ resolved (~10 + admission rule) · #67 README quickstart · #68 `--recommend` surfaces
  advisory skills · #69 dogfood the contribution loop. Gap-analysis skills: #42–#49.
- **Research complete:** all 12 areas + CEO-under-pressure + gap-analysis. CEO-under-
  pressure shipped in `agentic-ceo`'s chaos playbook.

*This document is provisional and updated as skills ship. Decisions #39 (vendor),
#40 (thin guides), and #66 (suite scale) are resolved and executed; #38 (rename)
remains deferred. The suite is 10 skills under a written admission rule (Architecture
§); #42 (product-output-safety) is the one admitted standalone candidate — skill #11.*
