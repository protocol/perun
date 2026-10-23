# Perun capability matrix

**Bottom line.** Of 18 capabilities, 12 ship, 5 are partial and 1 is a gap by design (compressed-prose and minimal-code modes). Against 50 rival pages read on 2026-10-16 (63 rows), 13 rows have a result on `perun-vs-rivals.md`, 1 has one only in the README and 49 are not measured; 9 of the 18 capabilities have no measured rival at all. The verified gaps most likely to matter to users: no secret-read rule in the destructive-command guard, no tool-output compressor, no host detection or per-host invocation table, no deterministic UX or accessibility runner, and a review that cost about 3.4 times the Anthropic toolkit's at a tied F1 (H7b). Ten improvements are ranked below by judged value over effort plus paid spend; the top five are estimated at $1.24 of model spend between them ($12.98 for all ten), taken from costs already on `perun-vs-rivals.md`.

## How to read this page

- **Scope.** The 18 capabilities the owner listed. Repo evidence is `origin/main` at `c097d01f` (release 1.586.0); rival pages were read on 2026-10-16 and every rival URL is in [`standards-index.md`](standards-index.md) (section "capability matrix rivals", dated 2026-10-16).
- **Repo status** is `Shipped` (a skill, script or command does it), `Partial` (the main mechanism the rivals offer is missing) or `Gap` (not shipped). It comes from reading the repo, not from the README.
- **Perun status** is `Measured` only when the rival has a result on [`perun-vs-rivals.md`](perun-vs-rivals.md) (cited as H1 to H11, §1 to §3); otherwise `Not measured`. One row is `Measured elsewhere` because its result sits only in the README.
- **Concrete gap** is what the rival's page says it does that this repo does not, checked against the repo with the commands in "Repo checks behind the gaps" after the capability sections. A rival's own numbers are marked vendor-reported and were not re-run here.
- **What this page does not do.** It does not rank Perun against any rival, and it ran no rival and no model benchmark. A README states intent, not behaviour. Stars and last-push dates are in the standards index; they are popularity signals, not quality evidence.
- **Renames.** H8 names `claude-code-safety-net` and H5 names `ccusage`; GitHub now redirects both to `kenryu42/cc-safety-net` and `ccusage/ccusage`. H5 records the ccusage version (20.0.34); H8 does not record the safety-net version, so H8 may not describe today's release.

## Summary

| # | Capability | Repo status | Rival rows | With a Perun result | Largest verified gap |
|---|---|---|---|---|---|
| 1 | Code review | Shipped | 4 | 2 (+1 README only) | Cost per review (about 3.4 times the toolkit's, H7b); no apply step (`--fix`) or GitLab posting; no packaged specialist agents |
| 2 | Product advice and discovery | Shipped | 3 | 1 | Filled-in thresholds and templates (the rival led on the rubric-free judge, H1d); no connectors |
| 3 | Delivery team (lanes, roles) | Shipped | 4 | 1 | No browser QA or deploy commands; no executable multi-agent runtime |
| 4 | CEO or orchestrator | Partial | 3 | 0 | No runtime; no adapters for the agent-teams hook events |
| 5 | Compressed prose, minimal code | Gap | 4 | 0 | Neither mode ships; a detector and an injection hook only |
| 6 | Token usage optimisation | Shipped | 4 | 0 | No tool-output compressor; no per-skill or per-MCP attribution |
| 7 | Evil-twin critic | Shipped | 3 | 1 | No chained multi-review pipeline; no one-command cross-vendor second opinion |
| 8 | Decision council | Shipped | 3 | 0 | No UI, chairman synthesis or layered aggregation |
| 9 | Output optimisation and safety | Partial | 4 | 2 | No eval or scan runner; no prose detector score |
| 10 | Delivery optimisation | Shipped | 3 | 0 | No speculative parallel checks, batching or stack awareness |
| 11 | Context management | Shipped | 3 | 0 | No itemised context view; no cross-session retrieval |
| 12 | Per-host and per-LLM suggestions | Partial | 3 | 0 | No host detection, per-host invocation table or model-policy explainer |
| 13 | Budget and spend tracking | Shipped | 4 | 1 | Claude Code transcripts only; no hard stop on spend |
| 14 | Code optimisation, all angles | Partial | 4 | 0 | Read-only: no apply step, no before-and-after benchmark |
| 15 | UX and product audits | Partial | 4 | 0 | No deterministic UX or accessibility runner; no browser run |
| 16 | Growth, positioning, business-ops | Shipped | 3 | 2 | Breadth and tool integrations |
| 17 | Destructive-command guard | Shipped | 4 | 2 | No secret-read blocking; no directory edit lock |
| 18 | Auto-update and install | Shipped | 3 | 1 | Plugin installs rely on host auto-update; adoption; the `npx skills add` path is unverified |
| | **Total** | 12 Shipped, 5 Partial, 1 Gap | 63 | 13 (+1 README only) | |

## 1. Code review

**Repo status:** Shipped. **Where:** `.claude/skills/deep-code-review/SKILL.md` (21 audit domains, A to W), `commands/review.md`, `.claude/skills/deep-code-review/references/compact-mode.md`, the opt-in PR workflow `.claude/skills/deep-code-review/templates/perun-review.yml`, and `.claude/skills/deep-code-review/scripts/post_review.sh` (posts a pending review; GitHub only).

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [Anthropic pr-review-toolkit](https://github.com/anthropics/claude-code/tree/main/plugins/pr-review-toolkit) | Plugin of six review agents: comment-analyzer, pr-test-analyzer, silent-failure-hunter, type-design-analyzer, code-reviewer, code-simplifier. | Measured: H7b (n=22, patch-only) ties on F1 (+.035 [-.031, +.120]) at about 3.4 times the cost per review ($.0551 against $.0162); §1 (37 cases) ties on bugs found. | Five single-purpose agents besides the code reviewer (tests, silent failures, comments, types, simplification). Perun ships no agents (no `.claude/agents` directory) and cost more per review in both runs. |
| [Claude Code `/code-review`](https://code.claude.com/docs/en/code-review-local.md) | Built-in skill: reviews the diff, a PR, a branch or a path at effort levels from `low` to `ultra`; `--fix` applies the findings; `--comment` posts inline comments on a GitHub PR or a note on a GitLab MR; runs as a background subagent. | Measured elsewhere: `README.md` (2026-10-12, 34 cases) shows equal recall (0.529 against 0.529) and verified precision 0.839 against 0.336; not on `perun-vs-rivals.md`. | `--fix` (Perun's review is read-only by default, full-map-principles.md principle 7, and `commands/review.md` has no apply flag), GitLab posting (`post_review.sh` has no GitLab path) and an `ultra` level that runs the review in the cloud. |
| [obra/superpowers](https://github.com/obra/superpowers) (`requesting-code-review`) | Workflow skill that runs between tasks, reviews against the plan, reports by severity and treats critical issues as blocking; `subagent-driven-development` adds a two-stage review (spec compliance, then code quality). | Measured: §1 (37 cases) ties on F1, every interval includes 0; $0.096 per review against Perun's $0.136. | No capability gap found in the pages read. The measured gap is cost per review. |
| [CodeRabbit](https://www.coderabbit.ai/) | Hosted service: reviews every PR automatically on GitHub and GitLab, learns from usage, offers Quiet, Chill and Assertive profiles, scores and routes PRs, summarises large diffs, scans for security issues and has a Slack agent. | Not measured. | Review on PR open with no setup, and PR triage. Perun's PR path is an opt-in workflow template that needs a model API key secret, a banlist and a pinned CLI version; it has no PR ranking and no chat surface. |

## 2. Product advice and discovery

**Repo status:** Shipped. **Where:** `.claude/skills/product-discovery/SKILL.md` (Mom Test interviews, riskiest-assumption gate, PMF survey, ICE) and `.claude/skills/product-discovery/scripts/discovery_check.py`, a runnable check that enforces only rules quoted from that SKILL.md against a JSON plan or readout. The skill ships evals and that script, no templates.

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [phuryn/pm-skills](https://github.com/phuryn/pm-skills) | "69 PM skills and 42 chained workflows across 9 plugins", from discovery to launch (README). | Measured: H1 and H1d. Rubric judge 0.850 [0.700, 1.000]; rubric-free judge 0.300 [0.100, 0.500] (1 win, 5 losses, 4 order splits), a loss on that judge and set. | Hands over filled-in kill thresholds, decision rules and complete briefs where Perun leaves blanks (H1d judge reasons), and ships 42 workflows and templates where Perun ships none (§3). |
| [anthropics/knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins) | Eleven role plugins; the `product-management` plugin writes specs, plans roadmaps, synthesizes user research, keeps stakeholders updated and tracks the competitive landscape. Plugins bundle skills, connectors, slash commands and sub-agents. | Not measured. | Connectors to team tools and slash commands; Perun's product skills ship neither (§3). |
| [deanpeters/Product-Manager-Skills](https://github.com/deanpeters/Product-Manager-Skills) | "77 battle-tested skills + 6 command workflows" (v0.84, CC BY-NC-SA 4.0), including a problem-framing canvas. | Not measured for discovery (measured only for positioning, see section 16). | Breadth of named PM frameworks (77 skills against Perun's one discovery skill). Its non-commercial license is why H1d did not commit its text. |

## 3. Software-house delivery team (lanes, roles)

**Repo status:** Shipped. **Where:** `.claude/skills/agentic-delivery/SKILL.md` (gated G0 to G10), the 11 hats in `.claude/skills/agentic-delivery/references/roles.md` (Conductor, Ops and Merge-Guard, Product Analyst, Architect, Implementer, Evil Twin, QA, Security, UX and Design, Release, Docs), lane scripts (`lane_guard.py`, `lane_cap.py`, `lane_liveness.py`) and `.claude/skills/agentic-delivery/templates/lane-preamble.md`.

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [obra/superpowers](https://github.com/obra/superpowers) | A fixed flow: brainstorming, git worktrees, writing-plans, subagent-driven-development (a fresh subagent per task with a review after each), test-driven-development, code review, finishing the branch. | Measured: H4 (7 tickets, n=3 per arm) merged 21 of 21 with 0 escaped defects for both; $0.210 per run (Perun) against $0.441. The tickets were small and multi-lane coordination was not tested. | No capability gap found in the pages read. The gap is distribution: it is in the plugin marketplace (H10, §3). |
| [garrytan/gstack](https://github.com/garrytan/gstack) | "23 opinionated tools" (repository description) run as a sprint: office-hours, plan-ceo-review, plan-eng-review, review, qa, cso, ship, land-and-deploy, canary, retro; each skill feeds the next. | Not measured. | Real-browser `/qa`, one-command `/ship` and `/land-and-deploy`, `/canary` post-deploy monitoring and `/retro`. Perun ships no browser tooling or deploy commands (§3). |
| [bmad-code-org/BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) | Agile AI-driven development: agents and workflows bring product, architecture, UX, development and testing perspectives; add-on modules include a Test Architect and a Creative Intelligence Suite. | Not measured. | Briefs, specifications and architecture as first-class workflow outputs. Perun's templates are lane preamble, host safety and review tiers, plus ADR and postmortem references; it has no product-brief or story templates. |
| [FoundationAgents/MetaGPT](https://github.com/FoundationAgents/MetaGPT) | Multi-agent framework that models a software company: a one-line requirement becomes user stories, competitive analysis, requirements, data structures, APIs and documents; roles are product managers, architects, project managers and engineers ("Code = SOP(Team)"). | Not measured. | Runs the roles as an executable program that passes structured documents between roles. Perun's hats are instructions an agent adopts plus gate scripts (§3: "prose plus helper scripts, not a runtime"). |

## 4. CEO or orchestrator running agents

**Repo status:** Partial. **Where:** `.claude/skills/agentic-ceo/SKILL.md` (routes stage and area to a skill), `.claude/skills/agentic-ceo/scripts/task_ledger.py` (durable owner asks), `commands/perun-run.md` (loops until the ledger drains), `commands/perun.md` with `.claude/skills/agentic-ceo/scripts/weekly_receipt.py` (weekly receipt), the typed board (`board_state.py`, `board_post.py`). There is no process runtime. H3 measures routing only (24 of 30 first-skill picks against 10 of 30 for Superpowers and for no pack; tuned on the same prompts, n=1 per prompt, Superpowers' hooks excluded).

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [Claude Code agent teams](https://code.claude.com/docs/en/agent-teams) | Experimental and off by default (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`): a lead plus teammates with a shared task list (dependencies, file-lock claiming), a mailbox, in-process or split-pane display, and `TeammateIdle`, `TaskCreated` and `TaskCompleted` hooks where exit code 2 blocks. Documented limits: no resume of in-process teammates, task status can lag, one team per session, same-file edits overwrite. | Not measured (§3 records the runtime gap; H3 and H4 do not test teams). | A running team with dependency unblocking and messaging. Perun has no adapter for the three team hook events (no match in the repo) and no runtime. |
| [ruvnet/ruflo](https://github.com/ruvnet/ruflo) (formerly claude-flow) | "An agent meta-harness for Claude Code and Codex": core tools, a visual console (the "agent cockpit") and mods that add routing and policy enforcement inside Claude Code. | Not measured. | A live console and routing mods; Perun's conductor is prose and scripts. |
| [OrchestratorInc/agent-orchestrator](https://github.com/OrchestratorInc/agent-orchestrator) | Local desktop workspace: one worker session per task with its own branch and worktree, a project-aware orchestrator, a live Kanban of workers, PRs, CI and review, any harness; updates itself. | Not measured. | Visual supervision across harnesses; Perun's typed board has no UI. |

## 5. Compressed-prose and minimal-code modes

**Repo status:** Gap, by design: neither voice nor bias text ships. **Where:** `.claude/skills/agentic-delivery/scripts/terse_reply_check.py` (opt-in Stop hook, `install.sh --with-terse-replies`, asks for a rewrite when the filler share passes 0.12) and `.claude/skills/agentic-delivery/scripts/subagent_start_inject.py` (injects a project-owned house-defaults file, with a `MINIMAL-CODE:` tag, into every subagent). `docs/technical-overview.md` points at the first two rivals below, and `install.sh` at the first.

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) | Terse-voice skill (`/caveman`, `/ultracave`) on controlled English, for 30+ agents. Vendor-reported: against an "Answer concisely" baseline `/caveman` cuts 3% more output tokens at the median and `/ultracave` 35% more (10 questions, one model); a JetBrains paired test of 86 tasks found no measurable quality loss and 8.5% fewer output tokens. | Not measured. | Ships the voice text with a status command and per-feature toggles; Perun ships a detector and an injection hook only. |
| [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | Minimal-code skill: a ladder (needed at all, already in the codebase, standard library, native feature, existing dependency, one line) with lite, full and ultra levels, `/ponytail-review`, `/ponytail-audit` and a status band in Claude Code. Its README reports a vendor benchmark of 39 tasks with one model and 5 runs each. | Not measured. | Ships the bias text and the commands; Perun ships only the injection hook. |
| [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) | One `CLAUDE.md` with four principles: Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution. | Not measured. | A drop-in file with no installer; Perun has no default instruction file for either mode. |
| [Claude Code Concise output style](https://code.claude.com/docs/en/output-styles.md) | Built-in style: "Responses lead with the result and leave out preamble, narration, and recaps." | Not measured. | A zero-install host feature; Perun's equivalent needs a flag plus a project file. |

## 6. Token usage optimisation

**Repo status:** Shipped for its own footprint and for measurement; there is no tool-output compressor. **Where:** progressive disclosure with frozen budgets (`scripts/mustload-budgets.tsv`, `scripts/size-budgets.tsv`), `.claude/skills/agentic-ceo/scripts/token_report.py` (main against subagent split, `--budget`), `token_ratchet.py`, `commands/cost-retro.md`, `.claude/skills/agentic-delivery/scripts/handback_cap.py`, `.claude/skills/deep-code-review/references/model-tiering.md` and `docs/token-cost-tips.md`. §2 measures the always-loaded footprint of whole bundles (Perun 921 tokens, rank 1 of 6), which is not a comparison with the three tools below.

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [rtk-ai/rtk](https://github.com/rtk-ai/rtk) | CLI proxy that filters and compresses command output before it reaches the model: "100+ supported commands, <10ms overhead", installed as per-agent hooks with `rtk init`. Vendor claim: 60 to 90% fewer tokens on common dev commands. Two editions (Apache-2.0 plus BUSL-1.1, and Apache-2.0 only). | Not measured. | Compresses tool output at the shell hook. Perun shrinks what it loads and caps handbacks but has no tool-output compressor. |
| [microsoft/LLMLingua](https://github.com/microsoft/LLMLingua) | Research library for prompt compression (LLMLingua, LongLLMLingua, LLMLingua-2; its README says LLMLingua-2 is 3x to 6x faster than LLMLingua). | Not measured. | Model-based compression of long prompts and retrieved context; Perun uses deterministic budgets only. |
| [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) (Blocks, Browse, Waste fixes) | Beyond the voice: "Blocks" (the agent keeps scripts it wrote and reruns them), "Browse" (web pages returned compressed) and "Waste fixes". Vendor-reported: 397 to 76 tokens for one test run and a 129.8x smaller page. | Not measured. | Compresses what the agent reads and reruns; Perun has no equivalent. |
| [Claude Code cost management](https://code.claude.com/docs/en/costs) | Documented levers: `/usage` (session cost, prompt-cache statistics, a plan breakdown attributed to skills, subagents, plugins and MCP servers), `/clear`, compaction instructions, model choice, deferred MCP tools, hooks that pre-filter output, effort level. | Not measured (Perun's own host-lever notes are in `.claude/skills/agentic-delivery/references/host-enforcement.md`). | Host-native attribution by skill, subagent, plugin and MCP server, and cache-miss flags. `token_report.py` splits main against subagents only. |

## 7. Evil-twin critic for decisions

**Repo status:** Shipped. **Where:** `.claude/skills/idea-critic/SKILL.md` (three hats: skeptic, better-way, kill-criteria; verdict `HOLD`, `REVISE` or `PASS_TO_USER`), `.claude/skills/idea-critic/scripts/validate_verdict.py`, and the Evil Twin hat in `.claude/skills/agentic-delivery/references/roles.md`.

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [garrytan/gstack](https://github.com/garrytan/gstack) (`/plan-ceo-review`) | "Rethink the problem. Find the 10-star product hiding inside the request." Four modes (Expansion, Selective Expansion, Hold Scope, Reduction); `/autoplan` chains CEO, design, DX and engineering reviews. | Measured: H1d (n=10) rubric judge 1.000 (rubric not preserved), rubric-free 0.650 [0.450, 0.850], FAIL: a tie the data cannot separate from a loss or a modest win. | Scope modes and a chained multi-review pipeline; Perun returns one verdict and does not chain reviews. |
| [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) | Runs Codex inside Claude Code: `/codex:review`, `/codex:adversarial-review` ("a steerable challenge review"), and rescue, status, result and cancel for background jobs. | Not measured. | A second opinion from a different vendor's model in one command; Perun's critic hats run on the host's model unless `council.py` is given another CLI with `--cmd`. |
| [Claude Code agent teams](https://code.claude.com/docs/en/agent-teams) | Docs examples: one teammate "playing devil's advocate"; teammates "try to disprove each other's theories" in a debate. | Not measured. | Adversaries that message each other live; Perun's hats are sequential passes or independent council calls with no inter-agent messaging. |

## 8. Decision council for complex decisions

**Repo status:** Shipped. **Where:** `.claude/skills/idea-critic/references/council.md` and `.claude/skills/idea-critic/scripts/council.py` (any model through `--cmd` templates such as `claude -p` or `codex exec -`; three independent lenses; a deterministic tally; a critique round only on disagreement; claims need `path:line` or a URL), tested by `scripts/test_council.py`.

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [karpathy/llm-council](https://github.com/karpathy/llm-council) | Web app: stage 1 first opinions from several models, stage 2 anonymized review, stage 3 a chairman writes the final answer; models through OpenRouter. Its README calls it a Saturday hack that the author will not support or improve. | Not measured. | A UI with per-model tabs and one key that reaches many vendors. Perun's council needs a command template per model and has no UI or chairman step. |
| [amgadelgamal/claude-council](https://github.com/amgadelgamal/claude-council) | Council of Claude subagents with personas (Architect, Skeptic, Pragmatist, Researcher), anonymized peer review and a chairman. Its README notes that every member is Claude, so independence comes from isolation and personas, not model diversity. | Not measured. | Packaged named personas and a chairman synthesis; Perun's tally is mechanical and writes no chairman text. |
| [togethercomputer/MoA](https://github.com/togethercomputer/MoA) | Mixture-of-Agents: layers of models whose outputs feed an aggregator. The repository description reports 65.1% on AlpacaEval with open-source models (vendor-reported). Last push 2025-01-07. | Not measured. | Multi-layer aggregation; Perun runs one independent round plus a critique round only on disagreement. |

## 9. Output optimisation and safety

**Repo status:** Partial. **Where:** safety of AI output that reaches end users is guidance only: `.claude/skills/product-output-safety/SKILL.md` (MAP, MEASURE, MANAGE with a human gate; never certifies safe) plus `.claude/skills/product-output-safety/scripts/output_safety_check.py`, a deterministic checker for the rules the skill states (inventory, human gate, unmeasured metrics, test rows, certification words, bare percentages, card, regimes) against the input facts; no eval or scan runner (§3). Output shaping has scripts: `.claude/skills/communication-structure/SKILL.md`, `status_update_lint.py`, `status_vocab_lint.py`, `.claude/skills/agentic-delivery/scripts/handback_cap.py` and `terse_reply_check.py`.

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | CLI and library to evaluate and red-team LLM apps; runs in CI. | Measured: H1 and H1b (product-output-safety against its red-team setup skill, run without tools). Rubric judge 0.550 [0.400, 0.700]; rubric-free 0.150 [0.000, 0.400] (set A) and 0.250 [0.100, 0.400] (set B): Perun lost on the rubric-free judge; the pair is partly a scope mismatch. | Executes evals and vulnerability scans. Perun's skill tells the agent to build evals but ships none (§3). |
| [guardrails-ai/guardrails](https://github.com/guardrails-ai/guardrails) | Input and output "guards" that detect, quantify and mitigate specific risks inside the application, plus structured-data generation. Its README (2026-07-06 entry) says validators move to PyPI packages and hosted remote inferencing is discontinued. | Not measured. | Runtime guards in the product's own code path; Perun's output safety is design-time guidance with a human gate. |
| [blader/humanizer](https://github.com/blader/humanizer) | Skill that rewrites AI-sounding text, with 26 detection patterns; its README says it edits for human readers and does not aim to beat AI detectors. | Measured: H1 and H1c (communication-structure, n=10). Rubric judge 0.800 [0.550, 1.000]; rubric-free 0.500 [0.250, 0.800], FAIL: a tie. | A rewriter with a fixed pattern catalogue. Perun's communication-structure forces BLUF and lints status updates but does not rewrite arbitrary text. |
| [conorbronsdon/avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing) | Skill with detect-only and edit-in-place modes, voice profiles and a bundled detector that scores text 0 to 100 (npm package and CI workflow). | Not measured. | A runnable detector score and CI gate (§3); Perun's communication-structure has no detector or score for prose. |

## 10. Delivery optimisation (merge train, CI gating)

**Repo status:** Shipped. **Where:** `.claude/skills/agentic-delivery/scripts/merge_train.py` (lands several green PRs as one verified union, bisects a culprit, applies a flake rule), `land_train.sh`, `train_land.sh`, `train_flake.sh`, `heavy_gate.py`, `.claude/skills/deep-code-review/scripts/ci_cost_lint.py` (flags workflows that waste runner minutes) and `.claude/skills/deep-code-review/references/merge-operations.md`. H11 measures Perun's own train on one simulated fixture; no rival queue was run.

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [GitHub merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) | Platform feature: queued PRs build in a temporary `merge_group` branch with the latest base plus the PRs ahead of them; a failing PR is removed and the rest rebuilt; settings for merge method, build concurrency, group size and wait time. | Not measured (H11 is Perun's own train). | Enforced by branch protection with no script to run, and parallel build concurrency. Perun's train is a script an operator or lane runs. |
| [Mergify](https://docs.mergify.com/merge-queue/) | Merge queue that tests each PR against the latest code, runs "speculative" parallel checks, batches several PRs into one CI run and has priority rules. Vendor claim: 60 to 90% lower CI cost. | Not measured. | Speculative parallel execution, batching and priority rules; Perun verifies one union and then bisects prefixes. |
| [Graphite](https://graphite.com/docs/graphite-merge-queue) | Stack-aware merge queue: validates a stack in parallel, offers a fast-forward merge setting and avoids rerunning CI already validated on the same change. | Not measured. | Stack awareness; `merge_train.py` has no handling for stacked PRs (no match for "stack"). |

## 11. Context management (autocompact, handoff)

**Repo status:** Shipped (1.586.0). **Where:** `.claude/skills/agentic-delivery/scripts/handoff_inject.py` (SessionStart on `compact`, `startup` and `clear`; re-injects the newest `.claude/handoff*.md`, at most 2 KB, framed as data), `context_nudge.py` (UserPromptSubmit nudge at 250k tokens), `install.sh --apply-operating-layer` (sets `autoCompactWindow: 200000` only when no settings file sets it) and `.claude/skills/agentic-ceo/scripts/task_ledger.py` (owner asks survive compaction). Nothing here is on `perun-vs-rivals.md`.

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [Claude Code compaction and context tools](https://code.claude.com/docs/en/context-window.md) | Host-native: `/compact` with focus instructions, automatic compaction, `autoCompactWindow` (100000 to 1000000 tokens, per the [settings reference](https://code.claude.com/docs/en/settings-reference.md)), rules for what survives compaction, and `/context` (a usage grid with optimisation suggestions, per the [command list](https://code.claude.com/docs/en/commands.md)). | Not measured. | Perun builds on these. The gap is `/context`'s itemised view: `context_nudge.py` reports only the total size. |
| [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) | Persistent memory plugin for Claude Code: lifecycle hooks capture tool-use observations, generate summaries, store them in SQLite and inject relevant context into later sessions; includes a search skill. | Not measured. | Automatic capture and search across sessions; Perun's handoff is one file the agent writes (2 KB cap) plus the ledger. |
| [mem0ai/mem0](https://github.com/mem0ai/mem0) | Memory layer for agents (library and service). Vendor-reported: LoCoMo 92.5 at 7.0K tokens and 0.88 s p50 latency. | Not measured. | A general persistent memory store with retrieval; Perun has no retrieval store. |

## 12. Per-host and per-LLM command suggestions

**Repo status:** Partial. No feature has this name; the nearest shipped pieces are `install.sh`, which prints one `safety:` line per installed host from `.claude/skills/agentic-delivery/templates/host-safety.tsv` and the next command to run (`scripts/perun_doctor.py`), `.claude/skills/agentic-delivery/scripts/host_safety.py`, the README's native install commands for Claude Code, Codex, Gemini CLI and Copilot CLI, and per-LLM guidance as prose and a tier table (`.claude/skills/deep-code-review/references/model-tiering.md`, `.claude/skills/agentic-delivery/templates/review-tiers.tsv`, `tier_gate.py`). There is no host detection, no per-host invocation table and no per-model suggestion output.

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [garrytan/gstack](https://github.com/garrytan/gstack) | `./setup --host auto` installs for every agent it detects; a per-host table gives support level, invocation form, whether safety is enforced or advisory, and the second-opinion CLI; a model policy picks reviewer and implementation tiers and a read-only `gstack-models` command explains the effective choice; a weekly check flags changed official model recommendations and retirements. | Not measured. | Host detection, a per-host invocation and enforcement table, and a model-policy explainer. Perun has none of the three (`install.sh` has no detection code). |
| [vercel-labs/skills](https://github.com/vercel-labs/skills) | `npx skills add`, `use`, `list`, `find`, `remove`, `update` and `init`; `-a` or `--agent` targets specific agents; its README says it supports "OpenCode, Claude Code, Codex, Cursor, and 75 more". | Not measured. | One installer that selects among about 79 named agents. Perun selects hosts by flag or fixed roots (19 hosts, H10). |
| [intellectronica/ruler](https://github.com/intellectronica/ruler) | One `.ruler/` source of truth applied to each agent's own rules file (for example `CLAUDE.md` for Claude Code, `AGENTS.md` for Codex), MCP settings, skill locations and subagent locations, targeted through `ruler.toml`. | Not measured. | Per-agent rules files, MCP settings and subagent locations from one source. Perun copies skill folders and writes one `AGENTS.md` pointer; it manages no MCP settings or subagents. |

## 13. Budget and spend tracking

**Repo status:** Shipped as reporting and soft caps; there is no hard dollar stop. **Where:** `.claude/skills/agentic-ceo/scripts/token_report.py` (main against subagent split, cost proxy from dated `DEFAULT_RATES`, `--budget` lane caps and an orchestration-share ceiling; reads Claude Code transcripts only), `.claude/skills/agentic-delivery/scripts/spend_report.py` (provider usage export grouped by key-name prefix), `lane_cap.py` (nudges at a tool-call cap), `.claude/skills/agentic-ceo/scripts/weekly_receipt.py`, `commands/cost-retro.md` and `perun_policy.py` (lane cap from the `tokens` setting).

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [ccusage/ccusage](https://github.com/ccusage/ccusage) | Reads local usage data from coding-agent CLIs into daily, weekly, monthly and session reports for Claude Code, Codex, OpenCode, Amp, Droid, Codebuff, Hermes Agent and pi-agent. | Measured: H5 (n=5 sessions, one machine) Perun's totals within 0.11% on 5 of 5 sessions (3 exact), cost within 0.35%. | Eight agent CLIs and live monitoring (H5 note). `token_report.py` has no Codex or other-host parser (no match). |
| [Maciek-roboblog/Claude-Code-Usage-Monitor](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor) | Live terminal monitor with forecasting and limit warnings; uses Claude Code's official statusline `rate_limits` when captured and labels local estimates otherwise. | Not measured. | Real-time burn rate and limit forecasting; Perun reports after the session. |
| [LiteLLM budgets](https://docs.litellm.ai/docs/proxy/users) | Proxy that records each request's cost and enforces `max_budget` per virtual key, team, member or user: "After the key crosses it's `max_budget`, requests fail". `budget_duration` resets it; needs a database. | Not measured. | Refuses requests once a budget is crossed. Perun's `--budget` and `lane_cap.py` warn or nudge; they never refuse a paid call. |
| [Claude Code cost tracking](https://code.claude.com/docs/en/costs) | `/usage` (session cost, cache statistics, plan breakdown), the status line, workspace spend limits, OpenTelemetry export and `--max-budget-usd`. | Not measured. | Organisation-level spend limits and OpenTelemetry export; Perun is per session and local. |

## 14. Code optimisation from all angles (performance, security, maintainability)

**Repo status:** Partial. **Where:** the review covers performance, security and maintainability as domains E, B and H (`.claude/skills/deep-code-review/references/domain-e.md`, `performance-db-cost.md`, `domain-h.md`), with `partition_diff.py` and `impact_map.py` for large diffs. It is read-only by default (full-map-principles.md principle 7): there is no apply-findings flag and no before-and-after measurement.

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [Claude Code `/simplify` and `/security-review`](https://code.claude.com/docs/en/commands.md) | `/simplify` reviews changed code for reuse, simplification and efficiency with four parallel review agents and applies the fixes; `/security-review` analyses the branch diff for injection, auth issues and data exposure. | Not measured. | Applies the fixes; Perun's review reports only. |
| [SonarQube](https://www.sonarsource.com/products/sonarqube/) | Code verification platform for IDE and CI: maintainability, reliability and technical debt, vulnerabilities and security hotspots, pass or fail quality gates, AI CodeFix suggestions. | Not measured. | Continuous debt tracking and quality gates over time; Perun reviews on demand and keeps no code-health history. |
| [codeflash-ai/codeflash](https://github.com/codeflash-ai/codeflash) | Python optimiser: LLMs propose optimisations, tests check correctness, benchmarks measure speed, then a merge-ready PR; `codeflash --all` for a whole codebase. | Not measured. | Measures speed and correctness before proposing a change. Perun's performance findings come from reading code; it runs no profiler or benchmark. |
| [garrytan/gstack](https://github.com/garrytan/gstack) (`/benchmark`, `/cso`) | `/benchmark` baselines "page load times, Core Web Vitals, and resource sizes" and compares before and after on every PR; `/cso` is a security audit; `/review` auto-fixes the obvious findings. | Not measured. | Per-PR performance baselines and auto-fix; Perun has neither. |

## 15. UX and product audits

**Repo status:** Partial. **Where:** review domain P: `.claude/skills/deep-code-review/references/product-ux-quality.md` with the `ux-*.md` files, `frontend-a11y.md` and `rendered-parity.md`; `.claude/skills/deep-code-review/scripts/parity_differ.py` (element-inventory parity), `token_differ.py`, `.claude/skills/agentic-delivery/scripts/surface_check.py`; a UX and Design hat in `roles.md`. There is no standalone UX-audit command, no browser run, and no script that runs axe or Lighthouse (`frontend-a11y.md` names them in prose only).

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | Design skill with 24 commands (`audit`, `critique`, `polish` and more), live browser iteration and 59 deterministic detector rules that its CLI and browser extension run with no model and no API key. | Not measured. | Model-free detector rules; Perun's UX bar is prose judged by the model. |
| [dequelabs/axe-core](https://github.com/dequelabs/axe-core) | Accessibility engine for WCAG 2.0 to 2.2 (A, AA, AAA) and best practices. Its README says it finds "on average 57% of WCAG issues automatically" and returns "incomplete" items for manual review. | Not measured. | A runnable accessibility engine; Perun names axe in prose but ships no wrapper. |
| [Lighthouse](https://developer.chrome.com/docs/lighthouse/overview) | Open-source audits for performance, accessibility, SEO and more, run from DevTools, the command line, a Node module or PageSpeed Insights. | Not measured. | Same: named in prose, not run. |
| [garrytan/gstack](https://github.com/garrytan/gstack) (`/design-review`, `/qa`) | `/design-review` audits and then fixes with atomic commits and before-and-after screenshots; `/qa` explores browser, API, CLI, job and webhook behaviour, writes failing regressions and verifies the fix. | Not measured (§3: Perun ships no browser tooling). | Real-browser exploration and screenshot evidence. |

## 16. Growth, positioning, business-ops

**Repo status:** Shipped. **Where:** `.claude/skills/growth-analytics/SKILL.md`, `.claude/skills/positioning/SKILL.md` and `.claude/skills/business-ops/SKILL.md` (SKILL.md and evals; each also ships a runnable check: growth-analytics `scripts/readout_check.py` tests only what the input pre-registers; positioning `scripts/positioning_check.py` checks a drafted statement or message house against the rules positioning states, using only keys the input carries; business-ops `scripts/bizops_check.py` checks runway, LTV:CAC, payback and margin arithmetic against limits the input states; no templates).

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) | MIT collection of marketing skills for agents: conversion optimisation, copywriting, SEO, analytics and growth engineering; partners fund it through disclosed tool integrations. | Measured: growth-analytics (H1d) rubric-free 0.700 [0.500, 0.900], FAIL (lower bound exactly 0.5); business-ops against its pricing skill (H1) 0.700 [0.500, 0.900], FAIL. | Breadth (conversion, copywriting, SEO) and a registry of tool integrations; Perun ships neither. |
| [deanpeters/Product-Manager-Skills](https://github.com/deanpeters/Product-Manager-Skills) | 77 skills and 6 command workflows (v0.84), CC BY-NC-SA 4.0. | Measured: positioning (H1) rubric judge 0.950 [0.850, 1.000]; not re-tested rubric-free (spend cap, H1d). | Breadth of named PM frameworks. Its non-commercial license kept H1d from committing its text. |
| [anthropics/knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins) | Eleven role plugins including marketing, finance and legal, each bundling skills, connectors, slash commands and sub-agents (the finance plugin lists Snowflake, Databricks and BigQuery). | Not measured. | Connectors and slash commands for finance, marketing and legal work; Perun's business-ops is educational prose that routes legal and tax questions to a professional. |

## 17. Destructive-command guard

**Repo status:** Shipped. **Where:** `.claude/skills/agentic-delivery/scripts/destructive_guard.py` (PreToolUse hook on Bash, string-level, never runs the command, `--selftest`), `pipe_mask_guard.py`, `bypass_guard.py`, `docs/host-safety.md`, `scripts/test-destructive-guard.sh`; the OS sandbox is switched on by `install.sh --apply-operating-layer`. H8: 30 of 32 dangerous strings blocked, 0 of 30 benign strings.

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [kenryu42/cc-safety-net](https://github.com/kenryu42/cc-safety-net) | Pre-execution hook that "blocks destructive commands and access to secrets such as SSH keys and `.env` files", parses what the command does and is "not a sandbox"; lists Claude Code, Codex, Cursor and other hosts. | Measured: H8 (named `claude-code-safety-net` there) Perun 30 of 32 [.799, .983] against 19 of 32 [.423, .745]; the version measured is not recorded. | Blocks reads of secret files (`.env`, SSH keys). `destructive_guard.py` has no secret-read rule (no match for env, ssh, secret or credential in the file). |
| [disler/claude-code-hooks-mastery](https://github.com/disler/claude-code-hooks-mastery) | Hooks tutorial repository covering 13 lifecycle events; its PreToolUse hook "Blocks dangerous commands (`rm -rf`, `.env` access)". Last push 2026-03-04. | Measured: H8, 13 of 32 [.255, .577]. | The same secret-file rule. |
| [garrytan/gstack](https://github.com/garrytan/gstack) (`/careful`, `/freeze`, `/guard`) | `/careful` warns before destructive commands (rm -rf, DROP TABLE, force-push) and hard-denies root or home recursive deletes and default-branch force-pushes; `/freeze` restricts edits to one directory. | Not measured. | A directory edit lock; `destructive_guard.py` has no directory-scope option. |
| [Claude Code Bash sandbox](https://code.claude.com/docs/en/sandboxing.md) | OS-enforced limits on the files and network domains shell commands can reach (macOS, Linux, WSL2); covers shell commands only, so file tools, MCP servers and hooks run outside it. | Not measured (H8 says to keep the sandbox on because the guard is not a boundary). | Enforces at the OS level, which a string check cannot. Perun switches it on through the operating layer; it does not replace it. |

## 18. Auto-update and install across hosts

**Repo status:** Shipped. **Where:** `install.sh` (0.2 to 0.6 s, 3 typed commands, 19 hosts, H10), `.claude/skills/agentic-delivery/scripts/perun_auto_update.py` (SessionStart and UserPromptSubmit hooks wired by `install.sh --apply-operating-layer`, which is on by default with `--with-delivery` when `jq` exists; policy key `auto_update`), the manifests `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` and `gemini-extension.json`, `scripts/perun_doctor.py` and `scripts/perun_uninstall.py`.

| Rival | What it does (read 2026-10-16) | Perun status | Concrete gap |
|---|---|---|---|
| [obra/superpowers](https://github.com/obra/superpowers) | The README installation section lists 16 harnesses, each with its own install step (Claude Code, Codex, Cursor, Gemini CLI, Copilot CLI, OpenCode and others). | Measured: H10. Perun lists 19 hosts (only Codex smoke-tested) against 16; install 0.2 to 0.6 s; uninstall left 0 files in the 1.583.0 release checks; superpowers has more adoption. | One native marketplace or UI install per harness, and adoption. Eight of Perun's 19 hosts are skill-folder copies. |
| [vercel-labs/skills](https://github.com/vercel-labs/skills) | One CLI that installs, lists, finds, removes and updates skills across about 79 agents (`npx skills update`). | Not measured. | A cross-vendor updater for any skill. Perun's auto-update covers Perun only, and whether `npx skills add` finds Perun's skills from this repository's layout is unverified. |
| [Claude Code plugin marketplaces](https://code.claude.com/docs/en/plugins/host-marketplace.md) | Background auto-update is off by default for a third-party marketplace; a user turns it on in `/plugin`, or an administrator sets `autoUpdate: true` in managed settings. | Not measured. | `perun_auto_update.py` is wired by the script install's operating layer, `.claude-plugin/plugin.json` declares skills only (no hooks), and `docs/getting-started.md` never mentions the plugin route, so a plugin install is updated only if the user enables host auto-update or updates by hand. |

## Repo checks behind the gaps

Run from the repository root. For `grep`, "no match" means exit status 1.

| Claim | Command | Result at `c097d01f` |
|---|---|---|
| Perun ships no agents | `ls -d .claude/agents agents` | both missing |
| `post_review.sh` has no GitLab path | `grep -c -i -E 'gitlab\|glab' .claude/skills/deep-code-review/scripts/post_review.sh` | 0 |
| The guard has no secret-read rule | `grep -n -i -E '\.env\|ssh\|secret\|credential' .claude/skills/agentic-delivery/scripts/destructive_guard.py` | no match |
| The guard has no directory scope | `grep -n -i -E 'freeze\|--dir\|scope' .claude/skills/agentic-delivery/scripts/destructive_guard.py` | no match |
| No adapter for the agent-teams hook events | `grep -rIn -E 'TaskCompleted\|TeammateIdle\|TaskCreated' --exclude-dir=.git --exclude-dir=bench --exclude=CHANGELOG.md --exclude=standards-index.md --exclude=perun-vs-rivals.md --exclude=capability-matrix.md .` | no match |
| `token_report.py` reads no other host's transcripts | `grep -n -i -E 'codex\|opencode\|gemini' .claude/skills/agentic-ceo/scripts/token_report.py` | no match |
| `token_report.py` has no per-skill, plugin or MCP attribution | `grep -n -i -E 'mcp\|attribut\|per-skill\|plugin' .claude/skills/agentic-ceo/scripts/token_report.py` | one match, a comment about cache writes |
| `install.sh` has no host detection | `grep -n -i -E 'detect\|--host' install.sh` | no match |
| `merge_train.py` has no stack handling | `grep -c -i stack .claude/skills/agentic-delivery/scripts/merge_train.py` | 0 |
| `council.py` has no chairman step | `grep -n -i -E 'chair\|synthes' .claude/skills/idea-critic/scripts/council.py` | no match |
| No script runs axe, Lighthouse or pa11y | `grep -rIl -i -E 'axe-core\|lighthouse\|pa11y' .claude/skills/*/scripts scripts` | no match |
| The plugin manifest declares no hooks | `grep -c hooks .claude-plugin/plugin.json` | 0 |
| `docs/getting-started.md` never mentions the plugin route | `grep -c -i plugin docs/getting-started.md` | 0 |
| `install.sh` writes only an `AGENTS.md` pointer, no per-agent rules files | `grep -n -i -E 'cursorrules\|clinerules\|copilot-instructions\|\.cursor/rules' install.sh` | no match |

## Limits of this page

- Rival facts come from READMEs and documentation pages read once on 2026-10-16. Where a page quotes its own numbers they are marked vendor-reported and were not re-run.
- Perun's status uses only `perun-vs-rivals.md` (plus one README exception). Its caveats apply: same-vendor judge, small samples, no rival installer or queue run, and the rubric-free re-tests still missing for two skills.
- The gap statements about Perun are greps and reads of `c097d01f`; a later commit can close them. Re-run the checks above before acting on a gap.
- The ranking below uses judged inputs (reach, evidence, effort). The paid-spend inputs are copied from costs already on `perun-vs-rivals.md`; the one derived figure is labelled.

## Top 10 improvements by user value per cost

Each item closes a gap verified above, and none claims a result: the last column is the measurement that would prove the change, with the outcome that stops the work.

**How the score is computed.** Score = value divided by cost.

- **Value (1 to 5)** = reach + evidence. Reach: 1 for a narrow or opt-in skill, 2 for an install path or overlay many users touch, 3 for the default path of most installs. Evidence: 0 for none, 1 for a gap verified against a rival above, 2 for a loss or documented gap already on `perun-vs-rivals.md`.
- **Cost** = effort in person-days + paid model spend in dollars divided by 10 (an assumption: $10 of spend counts as one day). Paid spend is copied from a cost already on `perun-vs-rivals.md` (H1d $1.24 for the product-discovery pair, H7b $3.42, H1b $6.22, H4 $0.210 per run) or is $0 when the proof is deterministic.
- Reach, evidence and effort are judgments, not measurements. The scores below are computed from them.

| Rank | Improvement | Closes | Value | Cost (days + $) | Score | Measurement that would prove it, and what stops the work |
|---|---|---|---|---|---|---|
| 1 | Verify and document `npx skills add` for Perun's 11 skills | 18 (adoption, H10) | 4 | 0.25 + $0 | 16.0 | In a scratch project, with the owner's approval to run third-party `npx` code, run it against this repository: pass if 11 of 11 skills are found and `scripts/perun_doctor.py` passes on the result. Stop if discovery needs a second copy of the skills (the repo forbids duplicates) and record "not supported". |
| 2 | Document how to keep Perun current on the plugin route (turn on marketplace auto-update in `/plugin`, or update by hand), beside the script route that `docs/getting-started.md` already covers | 18 | 3 | 0.25 + $0 | 12.0 | A mechanical check that the README or `docs/getting-started.md` names an update step for each native-install route (Claude Code plugin, Codex, Gemini CLI, Copilot CLI: 4 of 4), each confirmed on the vendor's page fetched that day. Today only the Claude Code step is confirmed (the marketplace-hosting page linked in section 18); a route whose step cannot be confirmed is listed "not verified". |
| 3 | A per-host table: how to start a review on each host, and whether its sandbox is enforced or advisory | 12 | 3 | 0.5 + $0 | 6.0 | A mechanical check that every row of `host-safety.tsv` has an invocation line (19 of 19), each confirmed against the vendor's own page fetched that day (the method H10 used), plus a smoke run where the CLI is already installed (Codex today). A host that cannot be confirmed is listed "not verified". |
| 4 | Filled-in default thresholds in product-discovery, labelled as assumptions with the evidence that would replace them | 2 (H1d) | 3 | 0.5 + $1.24 | 4.8 | Rerun the H1d product-discovery pair on 10 fresh scenarios with the same rubric-free blind judge: pass if the interval's lower bound is above 0.5 (H1d: 0.300 [0.100, 0.500]) and the skill's no-fabrication evals still pass. Revert if not. |
| 5 | Secret-read rules in `destructive_guard.py` (`.env`, SSH keys, cloud credentials) | 17 | 4 | 1 + $0 | 4.0 | Add at least 10 secret-read and 10 benign-read strings to the corpus in `scripts/test-destructive-guard.sh` (today 32 dangerous and 30 benign, bar 28 of 32 and at most 1 false positive): pass if the guard blocks at least 9 of the 10 secret reads with 0 false positives on the benign reads, with Wilson intervals as in H8. The H8 rival harness is not in the repo, so a rival comparison needs a new one and is optional. Ship as opt-in if a benign read such as an example env file cannot be allowed. |
| 6 | Prove and trim the default `/review` DIFF path | 1 (cost, §1 and H7b) | 5 | 1 + $3.42 | 3.7 | Score the shipped path of `commands/review.md` (no skill load) on the 22 H7b cases with the same blind verifier: pass if F1 stays tied with the toolkit (interval includes 0) and cost per review is at most 1.5 times the toolkit's ($.0162, so at most $.024). Keep the skill path and publish the price if cost is above 2 times. |
| 7 | An optional deterministic UX and accessibility gate (axe-core and Lighthouse when installed, a no-op otherwise) | 15 | 3 | 1.5 + $0 | 2.0 | A fixture of 20 seeded defects (10 an axe rule can find, 10 it cannot) and 10 clean pages: pass if the gate finds at least 8 of the 10 detectable defects with 0 false positives, and review tokens do not change. Stop on fewer than 8 or any false positive. |
| 8 | An executable eval scaffold for product-output-safety (a promptfoo-compatible config plus the sequencing and kill-switch rules the H1b judge cited) | 9 (H1b) | 3 | 1 + $6.22 | 1.85 | Rerun H1b on a fresh set with the rubric-free blind judge: pass if the lower bound is above 0.5 (H1b: 0.250 [0.100, 0.400]) and the config runs under promptfoo on the seeded cases. If the interval again includes 0.5, ship the template only (H1b's prose edit moved 0.250 to 0.400, not significant). |
| 9 | Detect and recommend an output filter such as rtk in the operating layer (reuse, do not build) | 6 | 3 | 1.5 + $2.10 | 1.75 | Build 5 small paired tickets (the H4 fixture is not in the repo), then compare tokens per PR from `token_report.py` with the filter and without: pass if the median drops at least 10% and merged and escaped-defect counts do not worsen (H4: 21 of 21 merged, 0 escaped). The $2.10 is 10 runs at H4's $0.210; the extra half day is building the tickets. Stop under 10% or on any new escaped defect. |
| 10 | Host detection in `install.sh` (list the hosts found and install for those) | 12, 18 | 3 | 2 + $0 | 1.5 | A fixture home with each of the 19 host markers: 19 of 19 detected and none on an empty home, with typed commands to first review at or below H10's 3. Keep detection project-level if it would need user-level config (`host_safety.py` reads project files only). |

**Below the cut** (same rule): rubric-free re-tests of positioning and contribution, which H1d left unchecked (score 1.25; evidence is 0 because they are unconfirmed wins, not losses); a measurement of `handoff_inject.py` after a forced compaction (1.20, with a $5 cap I chose); `token_report.py` parsers for other hosts (1.00); `--fix` and GitLab posting for reviews (1.00); agent-teams hook adapters (0.69; the $8.82 is H4's $0.210 times 7, the teams multiplier on the Claude Code costs page, times 6 runs); a merge-train run against GitHub's queue on the H11 fixture (0.67).

**Attack on this ranking.**

- *Skeptic:* the inputs are judged. Moving each input of each candidate one at a time (value plus or minus 1, effort doubled, paid spend doubled: 64 changes) left the top-5 set unchanged in 59 and the top-10 set unchanged in 55. The top-5 set changed in 5 of the 64 cases, always the same swap: item 6 (the `/review` proof) replaced item 3, 4 or 5 when that item's effort doubled (items 3, 4, 5) or it lost one value point (items 4, 5).
- *Better way:* if value matters more than cost, order by value instead: item 6 first (value 5), then items 1 and 5 (value 4). Start there.
- *Kill criteria:* each row ends with the result that stops the work. Items 1, 2, 3, 5, 7 and 10 cost no model spend; items 2 and 3 can ship together as one documentation change.
