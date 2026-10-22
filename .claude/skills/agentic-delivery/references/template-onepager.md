# One-pager template

Read this when G0 Intake turns a vague idea into a brief the owner can approve in one reply, or when `/idea` drafts one.

Routed from G0 (`SKILL.md`). Goals, non-goals and appetite are required at G0; this is the shape that records them,
plus the assumptions and the explicit list of what will not be built. Keep it to one page. Save it to
`docs/ideas/<short-name>.md` only after the owner confirms; build nothing before that.

```markdown
# <short noun phrase for the idea>

## Problem
<Who is blocked, what hurts today, and how we would know it is fixed. Two or three sentences.>

## Direction
<The chosen approach, and in one line why it beats the other directions that were considered.>

## Assumptions
| Assumption | Check (how and by when) |
|---|---|
| <something that must be true> | <the cheapest test that would show it false> |

## MVP scope
<The smallest slice that tests the riskiest assumption. A short list of what ships.>

## Not doing
- <a thing someone might expect, and will not be built in this round>

## Open questions
- <a question the owner or a test must answer; keep this short>
```

Rules: every assumption names a check; the Not-doing list has at least one entry (a brief that excludes nothing has
not chosen); run `idea-critic` on the draft before the owner sees it.
