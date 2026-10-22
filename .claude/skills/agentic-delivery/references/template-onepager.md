# One-pager template

Read this when G0 Intake turns a vague idea into a brief the owner can approve in one reply, or when `/idea` drafts one.

Routed from G0 (`SKILL.md`). Goals, non-goals and appetite are required at G0; this shape records them in the order
`idea-critic` attacks a claim (steelman, options, what must be true, kill criteria), so the critic can run on the
brief unchanged. Keep it to one page. Save it to `docs/ideas/<short-name>.md` only after the owner confirms; build
nothing before that.

```markdown
# <short noun phrase for the idea>

## Claim
<One line: the strongest version of the idea, who it is for, and the pain it removes.>

## Options weighed
| Option | Cost | Risk | Reversibility |
|---|---|---|---|
| Do nothing | | | |
| <cheapest alternative> | | | |
| <second alternative> | | | |
| **<chosen direction>** | | | |

Why the chosen one beats all three: <one line>.

## What must be true
| Belief | Cheapest check | Result |
|---|---|---|
| <something the idea relies on> | <the test that would show it false> | <open / held / failed> |

## First slice
<The smallest thing that ships and tests the riskiest belief above.>

## Not doing
- <a thing someone might expect, and will not be built in this round>

## Kill criteria
<One observable metric with a numeric threshold, a date, and the stop or pivot action when it trips.>

## Unresolved
- <a question the owner or a test must answer; keep this short>
```

Rules: every belief names a check; the Not-doing list has at least one entry (a brief that excludes nothing has not
chosen); kill criteria name a number and a date; run `idea-critic` on the draft before the owner sees it.
