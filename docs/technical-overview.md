# Technical overview

Read this when you want the engineering detail that used to sit in the top-level
[`README.md`](../README.md): the mechanisms table, the full "what you get" list,
fleet rules, how a review runs, token and context efficiency, and recent releases.
Nothing here is new; it moved out of the README so the README can be read by
anyone. Relative links below point at the repository root's neighbours.

## Problems it solves (mechanisms)

Each row is a shipped mechanism; the version is where
[`CHANGELOG.md`](../CHANGELOG.md) records it.

| Problem | Without Perun | With Perun | Since |
|---|---|---|---|
| A design port looks right but is incomplete | A pixel or size diff passes a page with a missing button or row. | `parity_differ.py` compares each section's element inventory (headings, text, controls, images, list rows) between design and app. Sizes are never inputs; one missing element shows completeness below 100%. A structurally wrong port fails even when the pixel difference is tiny. | 1.442.0, 1.447.0 |
| Subagents flood the chat | Every helper agent returns a long report, multiplied across a fleet. | A `SubagentStop` hook blocks a final message over 800 characters or 10 lines; the deliverable goes in a file. | 1.434.0 |
| Lessons stay advice | A lesson is written into the instructions and an agent skips it. | Perun's CI fails a commit that edits skill instructions without also touching a test, eval, or script, unless it states a `No-Mechanism-Reason:`. | 1.436.0 |
| "Deployed" is taken on faith | A green CI badge counts as proof the change is live. | `surface_check.py` compares the running app's build id with the commit; a missing id reports `COULD_NOT_CHECK`, never a pass. | 1.441.0 |
| Owner requests get lost | Asks disappear when an agent's context is compacted. | `task_ledger.py` keeps every ask verbatim; "done" needs evidence (a commit, URL, issue, or test id). | 1.442.0 |
| Tests pass until a date | A fixture built from a fixed "now" passes until the calendar crosses a threshold, then fails every branch at once. | The review flags the pattern and asks for an injected clock (or fixtures derived from the real clock) plus tests before, at, and after the threshold. | 1.446.0 |


## What you get

| Outcome | What it looks like |
|---|---|
| A report you can act on | Findings ranked Blocker → Critical → High → Medium → Low → Nit, each with `file:line` evidence and a fix. See the [fictional example report](example-review-report.md). |
| A summary for non-coders | A traffic-light health scorecard, the top risks in plain terms, and the decisions that need an owner. |
| Broad, fixed coverage | 21 audit domains (lettered A–W), an adversarial red-team pass, and a check for costly work that adds no value (repeated identical API/LLM/DB calls, over-fetching). |
| Lower context cost | The method files every review must read dropped from 65,903 to 28,025 estimated tokens (a FULL repo review: 87,137 to 36,096), about 57% less. A web review's must-read set dropped from 86,820 to at most 23,349. CI blocks either number from growing. |
| Checks that run, not just advice | 25 shipped gate scripts carry a `--selftest` that proves they catch a planted violation, run in CI on every change. `--with-gates` wires the review's own gates into your repo's CI. |
| A bar that stays | An optional final phase writes an `AGENTS.md` and pre-commit/CI gates into your repo, so the next contributor or agent, from any vendor, is held to the same bar. |

Where the numbers come from: token figures are characters ÷ 4, from
[`CHANGELOG.md`](../CHANGELOG.md) and the CI ceilings in
[`scripts/mustload-budgets.tsv`](../scripts/mustload-budgets.tsv); the domain count
is the domain map in
[`SKILL.md`](../.claude/skills/deep-code-review/SKILL.md); the script count is the
`.claude/skills/*/scripts/*.py` files with a `--selftest`, each invoked in
[`ci.yml`](../.github/workflows/ci.yml).


### Running agent fleets

The delivery overlay (`--with-delivery`, included in `--full`) and the
conductor overlay (`--with-ceo`) ship fleet rules as scripts that exit
non-zero instead of prose an agent may skip:

- **Handback cap:** an opt-in `SubagentStop` hook blocks a subagent's final
  chat message over 800 characters or 10 lines; the deliverable goes in a file.
- **Owner priority and ledgers:** `focus_gate.py` blocks work outside an
  owner-committed priority until its acceptance command passes or the work is
  blocked on someone else. `task_ledger.py` keeps every owner ask verbatim, so
  none is lost when context compacts.
- **Coordination:** isolation checks at lane start, claim tie-breaks, a
  cross-lane test lock, and a typed coordination board.
- **Merge train:** `merge_train.py` compares against freshly fetched refs and
  fixes a red base forward only under an owner-authored grant.
- **Proof of done:** `lane_guard.py handback` accepts a lane's claim only when
  the cited commit is the branch head and every cited file is committed at it;
  `surface_check.py` checks a "deployed" claim against the running build.

Every mechanism, what it blocks, and how to switch it on:
[`docs/for-fleets.md`](for-fleets.md).


## How it works

```
 you: "review this"
        |
        v
 +-------------+  reads    SKILL.md: the map (max 24 KB). Scope, phases,
 | your agent  | --------> severity scale, and which file to read when.
 +-------------+                  |
        |                         | routes on a stated trigger
        |                         v
        |  loads only    references/*.md: depth for security, data,
        |  what applies  accessibility, one file per language family ...
        |
        |  runs          scripts/: gates that answer with an exit code
        |                (fix has a test, no committed binaries, ...)
        v
 severity-ranked report: file:line evidence and a fix for every finding
```

The review runs in fixed phases: pin the exact commit, gather ground truth
(build, tests, lint), audit each applicable domain, run the adversarial pass,
then rank, deduplicate, and report. The full method, first-response block,
and domain map live in [`SKILL.md`](../.claude/skills/deep-code-review/SKILL.md).


## Token and context efficiency

Every token an agent reads costs money and crowds its working memory. Perun
keeps that load small:

- **Progressive disclosure.** `SKILL.md` is a map; depth sits in routed
  reference files loaded only on a stated trigger. Large references index their
  own sub-files, so a web review reads the accessibility basics and skips the
  data-pipeline depth.
- **Frozen budgets.** CI caps every skill map at 24,000 bytes, freezes each
  reference's byte size, and pins each review type's must-read token total.
  Raising a size budget needs an explicit `size-budget-raise:` marker.
- **Lookup tables, not browsing.** Every skill ships a generated `INDEX.md`
  (file → when to read it → estimated tokens → headings), so an agent opens one
  file instead of scanning references. CI fails when an index goes stale.
- **Short handbacks.** The handback cap and one-line reporting default stop
  per-lane narration multiplying across a fleet.
- **Measure and cap it.** `agentic-ceo/scripts/token_report.py --session <transcript>`
  reports main-agent vs subagent tokens and each subagent's startup and output
  cost. `--budget` adds per-lane caps (tool calls, tokens, startup overhead)
  and an orchestration-share ceiling (default 20%); each breach names the fix.
- **Host settings.** The verified Claude Code settings that cut per-turn tokens
  are documented in
  [`host-enforcement.md`](../.claude/skills/agentic-delivery/references/host-enforcement.md).
- **Optional companions.** For shorter assistant chat, add
  [caveman](https://github.com/JuliusBrussee/caveman); for a minimal-code bias on
  plumbing, bug-fix, and QA work, add
  [ponytail](https://github.com/DietrichGebert/ponytail) (pin a reviewed release;
  exempt design-port work, where exact fidelity and required tests beat minimal
  code). Neither is bundled. Code, PR bodies, and docs stay in normal English.


## What's new

The latest five releases; full detail in [`CHANGELOG.md`](../CHANGELOG.md).

- **1.461.0** — Critical work only: agents spend tokens just on the objective.
- **1.460.0** — Field-feedback wave: allowlist filters, load tests prove identity, heap slope.
- **1.459.0** — Deferred asks reported, never silently queued; build and interaction gates; per-row N+1.
- **1.458.0** — Renamed controls read as relabels, not removals; pre-push reuses a verified result for the same commit; stacked lanes branch from the local ref.
- **1.457.0** — Minimum-cost CI & token profile: integration branches skip hosted CI for a local deterministic gate; cost-vs-quality guardrails (tier gate, lane cap, escaped-defect trailers).
