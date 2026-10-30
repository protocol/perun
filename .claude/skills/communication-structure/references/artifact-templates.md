# Artifact templates and budgets

Read this when you draft a status update, PR body, release note, decision memo or executive summary, incident
summary, README section, or a tracker or PR comment. Each artifact has one shape, a word and line budget, and a check:
`python3 .claude/skills/communication-structure/scripts/comms_lint.py --kind <kind> --file <draft.md> [--source <notes.md>]`
scores every rule and prints the exact fix per failure (exit 1 = below the bar). With the operating layer installed,
`agentic-delivery/scripts/comms_guard.py` runs the same check before a PR or tracker write and warns with the fixes; it never blocks.

## Every artifact

1. **Line 1 is the answer:** outcome, the number, the ask; 30 words or fewer. No greeting, background or "This PR..." opener.
2. **Numbers before adjectives:** `p95 1.8 s → 35 ms`, not "much faster". An unknown figure is named as unknown ("insert overhead: not measured").
3. **An ask names its owner and date when the source gives them:** `Ask: Priya to approve by Tue 2026-10-20.` Speaking to the reader, address them ("Dana, please pick A or B by Tuesday"), not in the third person. The source gives no owner or date: leave that part out. Never write a stand-in such as `owner unassigned`, `no deadline` or `not stated`; readers rejected them as clutter (the lint fails them as placeholders).
4. **Status marks:** ✅ = verified, name the surface; ⏳ = pending. "Merged, unverified" is ⏳. Leave neutral facts (churn, risks) unmarked.
5. **Add nothing the source lacks:** no number, date, owner, recommendation, rationale, command or promise the author did not give. Keep an author's lean at the strength stated ("leaning B"), not "I recommend B". A derived figure shows its basis: `~15 min (11 min x 1.4)`. A weekday must fit its date (the lint computes it): if the source gets one wrong, say so instead of repeating it. Pass `--source` to check figures.
6. **Match the genre:** a PR body reads like a PR (headings are fine, never "Reply A or B"); a tracker comment is 2-4 lines; incident text is plain enough for a customer admin.
7. **Cut:** greetings, thanks, process narration, restated questions, filler adjectives, a closing summary. Keep every fact the reader needs to act on: a budget is a target, and the lint fails only above 1.5 times it.

## Budgets (comms_lint.py parses this table; edit here only)

| Kind | Words | Lines | Also checks |
|---|---|---|---|
| `status` | 150 | 14 | numbers, ask, markers, vocab, timezone |
| `leadership` | 220 | 24 | numbers, ask, structure, timezone |
| `pr` | 200 | 28 | numbers, askif, verified |
| `audit-pr` | 1200 | 160 | numbers, verified, sections |
| `release` | 120 | 14 | numbers, ask, vocab |
| `decision` | 200 | 22 | numbers, ask |
| `incident` | 220 | 24 | numbers, ask, vocab, timezone |
| `readme` | 200 | 30 | command |
| `message` | 200 | 20 | |
| `meeting-notes` | 250 | 30 | nolead, table, numeric, dri, links |

`nolead` drops the lead check (meeting-notes has no BLUF). Always checked: lead, budget, dates, filler, placeholder,
vague. Advisory (WARN, never below the bar): hedge, ask, markers, length (over the table value, under 1.5 times it),
numbers, verified, timezone. Nothing demands what the input lacks: `ask` (and `askif`, ask only when the text asks) runs
only with `--source` and only when the source has an ask, and flags a missing owner or date only if the source gives one. `status` with four
or more of the seven leadership labels is checked as `leadership`. Bodies under 60 words skip numbers, ask, markers,
verified and command. Fenced code does not count toward the budget.

`audit-pr` is the body of an audit, security or hardening PR. `sections` fails, at any length, when a required heading
(every heading of the template below except `Dependency upgrades`) is missing, `What changes for reviewers and users` is
empty (items, or `None`), or `Not fixed` carries a file:line, route, URL or file path (counts only). A closing footer
(`---` or `🤖 Generated`, then only blank, `Generated with` and `Co-Authored-By:` lines, any of them in `<sub>`, `<sup>`,
`<small>`, `*` or `_` markup) is not checked; other text after a `---` is. With `--range BASE..HEAD` it also fails when a changed file is not named under `Changes by area`, by full path
or by a containing directory with a trailing slash. The 1200-word, 160-line budget counts everything outside `Changes by area`, where an area may be a bullet or a `### <Area>` heading; each `### ` area fails above 200 words and the whole body above 3000 words. The guard hook picks this kind when the `gh pr create|edit` title says audit, security
or harden, and for `create` passes the diff against `--base` (default `origin/HEAD`).

## Templates

Angle brackets mark what you fill in; none may survive into the draft.

**status** (project or weekly update; tracker `save_status_update`)

    **<Project>: <state>, <X of Y> (was <Z>), <date>.**
    ✅ <outcome>, verified on <surface>. <owner, date if given>
    ⏳ <pending item>. <owner, due date if given>
    <Reader>, please <decide A or B> by <date>.   |   (no ask: omit the line)

A leadership update for non-technical readers uses the seven labelled sections in `references/leadership-status-update.md`.

**pr** (also `gh pr create`, `gh pr edit`)

    <What changes + measured effect + what the reviewer must do. One sentence.>
    **Why:** <problem, with a number>.
    **Change:** <up to 4 bullets: area, effect>.
    **Risk and rollback:** <blast radius>; <exact rollback>.
    **Verified:** ✅ <check → result>  ⏳ <not verified; owner, date>
    <Reviewer>, please <approve or decide> by <date, if given>.   |   (no ask: omit the line)

**audit-pr** (an audit, security or hardening PR, picked by its title: reviewers see what changes before they open the diff; heading names are `AUDIT_SECTIONS` in `comms_lint.py`)

    ## Summary
    <What this PR does and the one review ask, 2-3 sentences; the first sentence 35 words or fewer.>
    ## What changes for reviewers and users
    - <Each noticeable change in plain words: a route that now needs sign-in, a new limit or timeout, an upgraded dependency, a changed dev workflow, a new config or env var, a changed error message.>   |   None
    ## Changes by area
    - **<Area>:** <what changed>. Why: <the risk in plain words, no exploit steps>. Files: `<path>` or `<dir>/`. Test: <the test that covers it>.
    ## Dependency upgrades
    - <Package: old → new>: <why>; <breaking notes>.   |   (nothing upgraded: omit the section)
    ## How to verify
    ✅ <check → result with counts, run on this exact head>  ⏳ NOT RUN: <what and why; what the reviewer should run>
    ## Not fixed
    <Counts by severity only, tracked privately: `2 high, 5 medium`. No file:line, route or exploit detail.>

Every changed file appears under `Changes by area`, itself or its directory. Claim in `How to verify` only what a log or commit backs.

**release** (release note, changelog entry, customer announcement)

    **<Product> <version>: <user-visible change>, <number>.**
    - <change>: <who it affects>, <effect with number>
    **Action:** none.   |   **Action:** <who> must <do X> by <date, if given>.

**decision** (decision memo, or the executive summary of a long report)

    **<Conclusion or recommendation>. <The number that carries it>.**
    - <Finding or option A, with its number: cost, time, count>
    - <Finding or option B, with its number>
    - Not known: <the gap that could change the answer>
    <Reader>, please <decide or approve X> by <date, if given>.   |   (no ask: omit the line)

Write "Recommend A" only when the author gave a view; otherwise "Decision needed between A and B". Keep every
finding and option trade-off that changes what the reader does; the rest stays behind a link.

**incident** (customer-facing summary)

    **<Service>: <impact> from <start> to <end> <time zone> (<duration>); <current state>.**
    - Impact: <who, how many, what broke>
    - Cause: <one sentence, only if confirmed>
    - Fix: ✅ <done>  ⏳ <pending; owner, date>
    **Customer action:** none.   |   **Customer action:** <do X> by <date>.

**readme** (one section)

    <What it does and for whom. One sentence.>
    `<the one command>`
    <Expected result, with a number.>

**message** (tracker or PR comment, reply): the answer or ask first in 30 words or fewer, then at most three supporting lines.

**meeting-notes** (agent-written meeting or standup notes in a shared doc). This kind has no BLUF, emoji or status key.

    <number> <decision>                       one short numeric line per item, each fact once
    | Item | Needs | Notes | Next steps |
    | [#123](url) | Decide: X vs Y | status goes here | DRI: Wen, by 2026-10-20 |
    Decided: <one line> ([where the work lives](url))

- Write in the doc the user names, as suggestions (suggest mode), never a local draft. While the user co-edits, target the latest revision, not a fixed one.
- No appendix sections (plans, other, sources, not found); caveats stay in your working notes.
- Open items are rows of the existing table, never bullets above it; each row asks one question; status goes in Notes.
- Before listing an item as open, search for a later decision. A decided item says `Decided:` and links the work, with no old-plan history.
- The DRI is never blank: `DRI: not set`. Every issue or PR number and tracker key is a link.
