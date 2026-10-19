---
name: communication-structure
description: >-
  Use BEFORE sending any human-facing message (PR body, issue/PR comment,
  status update, reply) or producing a report, plan, doc, summary or table.
  Forces BLUF, one ask, core value only, zero AI-slop before you draft. Skip
  for chat with the user, which keeps its house voice.
license: MIT
metadata:
  author: deep-code-review contributors
  version: "1.2.4"
---

# Communication structure

Governs the *structure* of anything a human reads without you there to
narrate it — a message (PR body, issue/PR comment, status update, reply) **or a
deliverable** (a report, plan, doc, summary, table). Same prose-voice boundary as
`idea-critic`: persisted artifacts stay normal English, never compressed chat
shorthand. This is about shape and length, not vocabulary. Lookup table:
`INDEX.md`; read it instead of opening references blindly.

## The rule

- **BLUF.** Line 1 is the answer: the outcome, the number, the ask, in 30 words
  or fewer. Everything after it is support the reader can skip without losing
  the decision. No greeting, background or "This PR..." opener.
- **One decision, explicit.** An ask names its owner and date when the source
  gives them ("Dana, please pick A or B by Tuesday"), addressed to the reader;
  with none given, leave them out; stand-ins ("owner unassigned") fail
  `comms_lint.py`. A message ends on the ask. A PR body asks in its own words;
  "Reply A or B" is for messages, never PRs.
- **Add nothing the source lacks.** No number, date, owner, recommendation,
  rationale, command or promise the author did not give. Keep an author's lean at
  its stated strength ("leaning B", not "I recommend B"); with no view given, name the
  options and who decides. A derived figure shows its basis; an unknown is
  named ("insert overhead: not measured"). `comms_lint.py --source` checks this.
- **Per-artifact shape and budget.** Status update, PR body, release note, decision
  memo or executive summary, incident summary, README section, comment, meeting notes: read
  `references/artifact-templates.md` before you draft. `comms_lint.py --kind <kind>
  --file <draft>` scores each rule and prints the exact fix (exit 1 = below the bar).
  The operating layer's `agentic-delivery/scripts/comms_guard.py` hook runs it
  before a PR or tracker write and warns; it never blocks.
- **Under 30 seconds.** ~150 words by default; the budgets in the reference
  are the ceilings. Longer needs a reason per block, or a cut.
- **Scannable.** Bold the one load-bearing sentence. Short paragraphs. A list
  only when every item is parallel and load-bearing; keep the 1-2 open
  questions that change the decision and push the rest to the doc or PR.
- **Their next action, not your process.** Drop the reasoning trail; give what
  changes what the reader does next.
- **A stakeholder-facing update states verified present-tense outcomes only:**
  what works on the surface they use, in plain value terms, checked there before
  you write it (✅ = verified, names where; ⏳ = pending; neutral facts unmarked).
  No effort counts ("12 tasks", PRs, "% complete") and no "coming next week".
- **Status updates for leadership (tracker project updates, issue status comments,
  owner hand-offs) use a fixed seven-part structure.** Read
  `references/leadership-status-update.md`; `scripts/status_update_lint.py` checks it.
- **Status vocabulary: merged, deployed, verified-on-<page> are distinct.** "live",
  "shipped to users" and "done" claim the last one and need a `verified-on-<page>`
  or `journey:` reference nearby; else say "merged" or "deployed, unverified".
  `scripts/status_vocab_lint.py --file <update.md>` flags the rest.
- **Numbers over adjectives.** "40s to 6s" beats "significantly faster." A
  headline metric states the **exact measured value and the exact target on the
  same line** (`X / Y`, `X of Y`), computed at report time, never rounded toward the
  desired outcome. Only descriptive language ("mostly," "on track") with no
  paired numbers is incomplete. If the exact number is unknown, say so.

## Deliverables, not just messages

The message rules apply to a **deliverable** (report, plan, doc, table) except the
30-second cap: it is **as long as its content requires and no longer**. BLUF still
comes first, every section earns its place, and *Cut on sight* applies in full: no
filler, no restated prompt, no marketing adjectives, no summary-of-the-summary.
This is the suite's no-slop output contract; other skills link to it.

## Cut on sight

"You're right" / "great point." Hedges ("it depends", "I think maybe", "could
potentially") — but **keep material uncertainty**: "the sync may not have run; its
log is unavailable" is evidence, not a hedge. Cut the reflexive qualifier, never
the honest unknown. Restating the question. Filler adjectives ("comprehensive",
"robust", "seamless"). A summary of the summary. Take a position only if the author
gave one; if two are live, name both and who decides.

## Sanity check

1. Read line 1 alone. Does it stand as the whole message? If not, promote it.
2. Count the asks. More than one → split, or pick the one that blocks the reader.
3. Every paragraph after the first changes what the reader does, or it's cut.
4. Every number, date and name is in the source. Run `comms_lint.py`.

## Before → After

**Status update.**
Before: "So I looked into why the dashboard was showing no data. I checked a few
things... I think the nightly sync job isn't running after a deploy... Not 100% sure,
but running it manually should fix it — let me know if you want me to try."
After: "Deploy succeeded; the dashboard is empty because the nightly sync never ran
after it. **Running it now. Please confirm production, not staging, today.**"

**PR body.**
Before: "Thanks for looking! There are kind of two ways to go on the empty state..."
After: "Empty state: skeleton loader (matches the app) vs. a 'no data yet' message
(clearer for new users). **Wen, please pick one.**" (the author's
lean, if any, stays as stated; no invented recommendation, date or stand-in)

**Stakeholder update.**
Before: "12 tasks done, 40 PRs merged. The export button is live. Saved filters ship next week."
After: "**The export button works for customers: verified-on-the-dashboard export page.**
Saved filters: no date promised." (effort counts and the promise are dropped; an
unchecked claim is flagged in the lead, never asserted)

**Progress status, exact vs. flattering.**
Before: "Strong progress — we've closed the vast majority of the open items."
After: "**<closed> / <total> backlog items closed.** Owner-blocked ones listed
below." (the real counts go in place of the placeholders)
