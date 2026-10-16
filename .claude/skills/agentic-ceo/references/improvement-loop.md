# Improvement loop: what should we build or fix next?

Read this when the owner (or you) asks what is most impactful, what else to improve or add, or for a roadmap, for any product including this one. Run it on a cadence (for example once per release train), not once. It extends the conductor; it adds no skill.

**BLUF.** Strategy first, then evidence, then a scored list that an adversary has attacked. One script (`scripts/roadmap_rank.py`) does the arithmetic and renders the fixed output order: strategy context, rejected items with reasons, ranked roadmap, ADRs, tracker issues.

Covered elsewhere, so not repeated: whether one idea is worth building (`product-discovery`), what to measure (`growth-analytics`), attacking a proposal (`idea-critic`), turning one signal into a spec (the Product Analyst hat in `agentic-delivery`'s `roles.md`), how Perun improves its own skills (`docs/self-improvement.md`). This loop ranks across all of them.

## 0. Strategy context (always first)

Read the README, any VISION, roadmap and PRD files, `CLAUDE.md` or `AGENTS.md` and the open-decisions list. Record five fields, each with a source (a path or link) or `assumed: <why>`:

- **Stage**: `prototype`, `mvp`, `growth` or `mature`, the model in `deep-code-review` (Project stage); name the signals you read. Never `growth` without a product-market-fit read (`product-discovery`): without one use `mvp` at most, because scale and acquisition before a fit read is the failure `growth-analytics` names. This weights what to build next; `deep-code-review`'s stricter default for review demands is unchanged, and the floor (security, secrets, data loss) never relaxes at any stage.
- **Vision**: what the product is for and what "better than rivals" means.
- **North star**: one customer-value metric with an existing instrument (`growth-analytics`). With no instrument the metric is `UNVERIFIED` and building one is a candidate item.
- **Direction** and **constraints**: the stated bets, budgets, policies, hard rules and work already in flight.

A missing field gets an explicit `assumed:` value, and the owner gets ONE batched question covering every assumed field (an absent owner: `task_ledger.py defer` with the default). Continue on the assumption; a correction just re-runs the script.

## 1. Right-size, then gather

- **Direct** (the default for a small or early project, or when the evidence fits one context): the CEO reads the sources and applies each relevant role's brief in turn. No lanes.
- **Fan out** only for large or independent read-mostly sources: one lane per relevant role, writing nothing but its return file, on the cheapest model tier that can read and extract. Gathering is mechanical; merging, scoring and judging stay with the CEO. Skip a role with no evidence source and say so in `sources`.

Sources. An absent or unreadable one is listed as `none present` or `UNVERIFIED: <reason>`, never skipped:

| Source | How | Rule |
|---|---|---|
| Issues and PRs | forge API or `gh`; where `gh` fails TLS, `agentic-delivery`'s `scripts/gh_rest.py` | counts, age, labels |
| Changelog and releases | `CHANGELOG.md`, release notes | reject work that already shipped |
| Feedback files, surveys, support threads | the repo's feedback ledger, exports | counts only, never identities |
| Analytics | the owner's own instruments | none present means say so; never estimate |
| Session logs and token reports | `scripts/token_report.py`, `scripts/weekly_receipt.py` | aggregates only; never paste session content into a public doc |
| Rival changelogs and releases | fetch live (releases API or raw changelog); cite URL and date | a rate limit or denial is `UNVERIFIED`, never filled from memory |
| The product's own benchmarks, CI and gate health | the repo | measured results beat opinions |

| Role | Looks for | Applies | Reads | Skip when |
|---|---|---|---|---|
| CPO | what users need that the product lacks or does badly; the riskiest untested assumption | `product-discovery`, `growth-analytics` | feedback, issues, support, analytics, retention | no users and no stated user problem |
| CTO | defects and debt that slow or endanger delivery; architecture limits | `deep-code-review` (health, architecture), `agentic-delivery` (speed) | review findings, test and CI health, hotspots | no code |
| CFO | spend that buys no outcome: tokens, cloud, lane waste | `business-ops` Lane A, token reports | `token_report.py`, spend exports | no spend data |
| CMO | where rivals or the market moved; claims that outrun evidence; distribution gaps | `positioning`, `growth-analytics` | rival releases (live), the benchmark page, README claims | no external audience yet |
| CISO | harm paths: secrets, host safety, unsafe AI outputs | `product-output-safety`, `deep-code-review` security | security findings, safety docs | nothing sensitive and no AI output reaches users |
| COO | friction in shipping: merge train, CI and hook time, lane failures | `agentic-delivery` | CI timings, train logs, handbacks, peer reports | single-writer work with no gated delivery |

Brief for any role (fill the row's cells; paste `agentic-delivery`'s `templates/lane-preamble.md` too):

```text
Read-only research lane. Role: <ROLE> (looks for: <Looks for>). Strategy context: <the five fields>.
Read: <Reads>. Apply: <Applies>. Write nothing except the return file <path>.
Return a JSON array, one object per recommendation, with exactly: id (slug), title, role, lever
(learning|reliability|velocity|growth|scale|cost|polish|security), evidence [paths, links or tag:ref],
reach + reach_src, impact + impact_src, effort + effort_src,
metric (baseline, target, how measured; it has a number), risks.
Every *_src is a link or "assumed: why". Never invent a number. A source you cannot read is UNVERIFIED.
Market size, legal and tax questions are routed to the owner, never entered as reach. At most <N> items, best first.
Final message: status | file | next.
```

## 2. Cluster and dedupe

Group the evidence by underlying user problem, not by symptom or role: one item per problem. Merge the same problem returned by two roles into one item and record `merged_from`. The script fails on a duplicate `id` and flags near-duplicate titles. Drop what already shipped (check the changelog and the code; record it as `reject: already shipped <ref>`). Work already in flight gets `status: in_flight`: it is still scored and shown, flagged, so a misallocation is visible. Add `vision`, `vision_reason`, `where`, `done_when`, `verify` (open items), each `gate` (an owner approval, a paid run or an external send; a list for several) and `wait_days` for a calendar wait.

## 3. Score (the script)

`python3 .claude/skills/agentic-ceo/scripts/roadmap_rank.py <input.json> [--strict] [--update docs/roadmap.md]`. The input shape is in the script's docstring; a CSV carries items only, with `--context` for the rest. The report prints the formula and the stage-weight table it used, and the script holds the only copy of the weights. The rules that matter:

- `reach` is a 1 to 5 share of our own users or runs, never a market size.
- `reach` counts our own users or runs touched. An item that only helps later rankings (a survey, a dashboard) touches only its respondents; "it informs every later ranking" is not a reach.
- `confidence` is computed, never typed: 1.0 when both reach and impact cite a real locator (a URL, an existing repo path or an issue or PR; a committed measurement, survey row or issue), else 0.5. `assumed`, `estimate:`, `~assumed` or any other text counts as assumed, so wording cannot bypass it. The report lists the assumed inputs per item; if every reach is assumed, say so: the order is a hypothesis.
- Owner gates and waits are priced into effort: +2 lane-days per owner approval, paid run or external send, +0.25 per calendar-wait day. A gated item does not rank as if it could start today.
- Equal scores rank fewer assumed inputs first, then lower effort, then id, so evidence-backed items beat guesses.
- The loop scores itself, which departs from `product-discovery`'s "the user supplies the numbers": that rule guards external facts (market size, quotes, PMF verdicts), which stay routed. Internal estimates may be self-scored only because the report prints which inputs are assumed and the formula penalises them.
- Stage changes the weights (pre-fit favours learning and core reliability over polish, scale and growth); vision gates the item: `aligned` 1, `partial` 0.5, `misaligned` (it contradicts the vision, the direction or a constraint) is rejected with the stated reason.
- `product-discovery` names ICE for a solo builder. This adds reach and divides by effort because it ranks many sourced items; set every reach to 1 to fall back to an ICE-like order.
- Same input, same output. Re-run after any change.

## 4. Attack the top 3

Run the `idea-critic` hats on each of the top 3: inline for low blast, independent for owner-decision grade. Embed each verdict object as the item's `critic` and check it with `idea-critic`'s `scripts/validate_verdict.py` when installed. `HOLD` moves the item to the rejected list with the reason; `REVISE` is revised and re-run at most twice, else it stays flagged unresolved; `PASS_TO_USER` needs a real `strongest_attack_survived`. After a `HOLD` the new top 3 needs a critic, so re-run until `--strict` exits 0. The script prints `UNVERIFIED` for a top-3 item the critic has not seen.

## 5. ADRs (CTO)

For accepted items that need a technical choice, not every item, write short ADRs covering architecture, development pipeline and tooling, each linked to the item it serves. Use `agentic-delivery`'s `references/template-adr.md` (context, considered options with trade-offs and do nothing, a "We will ..." decision, consequences) plus one reversal-cost line (one-way or two-way door: `idea-critic`'s `references/decision-hygiene.md`). Status stays `proposed` until the owner accepts. An ADR for a rejected item fails the script.

## 6. Output

The script renders a BLUF and then, in this order: 1 strategy context (with the evidence base and the one owner question), 2 rejected items with reasons, 3 the ranked roadmap (formula, sourced-or-assumed inputs, a success metric and evidence links per item, the critic results), 4 ADRs, 5 tracker-ready issues. Issue priority comes from rank and `P0` stays a human call; the issue fields are Where, Done when, Verify, Why, metric, evidence, risks and gate (tracker mapping: `agentic-delivery`'s `references/work-tracking.md`). Commit the input and the rendered report so the next run can check which shipped items moved their metric; "done" on an item is its own `verify` command, not a status line.

## Anti-rationalization (excuse, then rebuttal)

| Excuse | Rebuttal |
|---|---|
| "The backlog is obvious, skip the strategy step." | A ranking means nothing without stage and vision; the items they reject are the random builds this loop exists to stop. |
| "Estimate reach so the table has no gaps." | Mark it `assumed`; confidence drops to 0.5 and the report lists it. An invented reach is fabricated evidence. |
| "Run all six roles to be thorough." | Run the relevant ones; a role with no evidence source returns noise and burns tokens. |
| "Rank by the loudest feedback." | Loud is one source: cluster by problem, then score. |
| "Skip the critic, the top item is clearly good." | The top 3 are what the owner will act on, so an unattacked claim costs most there. |

Standards by name, no figures cited: RICE and ICE prioritisation; architecture decision records (Nygard, MADR). Fetch and log a source before citing a specific figure.
