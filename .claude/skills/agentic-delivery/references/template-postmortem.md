# Postmortem template

Read this when G10 or an incident meets `retrospective.md`'s mandatory-trigger
criteria and you must write the blameless postmortem (impact, root cause, actions).

Routed from G10 (`SKILL.md`) and `retrospective.md`. Copy this into the
target repo for any incident meeting the mandatory-trigger criteria in
`retrospective.md`. Blameless: assumes everyone involved had good intentions
and acted on the information they had at the time.

```markdown
# Postmortem: <one-line incident name>

**Status:** Draft | Reviewed | Complete
**Incident date:** <YYYY-MM-DD>
**Author(s):** <name(s)>
**Postmortem owner:** <name — accountable for driving action items to closure>

This postmortem is blameless: it assumes everyone involved had good
intentions and acted on the information they had at the time. Findings
point at systems and processes, never at a person. You can't fix people;
you can fix systems and processes.

## Trigger — why this postmortem exists

State which criterion fired (one or more): user-visible downtime/degradation
past threshold · any data loss · on-call intervention required (rollback,
traffic reroute, etc.) · resolution time above threshold · the problem was
found by a person, not by monitoring · a stakeholder asked for one anyway.

## Summary

<2-3 sentences: what broke, for how long, at what severity.>

## Impact

<Who/what was affected, how badly, for how long, and any measurable cost —
users affected, requests failed, data lost, revenue/SLO-budget impact.
Quantify; "some users noticed issues" is not impact.>

## Root cause(s)

<The systemic condition(s) that made the incident possible — not just the
proximate trigger. Multiple contributing causes are normal; list them all,
don't collapse to one for narrative neatness.>

## Trigger (technical)

<The specific event that activated the root cause(s) — a deploy, a config
change, a traffic spike, an expired credential, etc.>

## Resolution

<What actually stopped the bleeding and restored service — in the order it
was done, including anything tried that did NOT work.>

## Detection

<How was this noticed — paged by an alert (name it), a dashboard someone
was watching, a user report? If detection was manual/slow, that is itself
a finding — was there a golden-signal/burn-rate alert that should have
fired and didn't?>

## Action items

| Action | Type (mitigate / prevent / process) | Owner | Bug/issue | Done when (verifiable) | Status |
|---|---|---|---|---|---|
| | | | | | Open / In progress / Done |

Every action item is owned and tracked to closure — an item with no owner,
tracking id or verifiable end state is not done
(`python3 .claude/skills/agentic-delivery/scripts/prevention_lint.py FILE.md` fails it). If this root cause has appeared in a
prior postmortem, the missing action item is the finding: name which
regression test, alert, or gate should have existed and did not.

## Lessons learned

**What went well** — <existing detection/mitigation that worked as intended>
**What went poorly** — <gaps that let this happen or made it worse>
**Where we got lucky** — <what would have made this materially worse, that
didn't happen this time — don't let luck get filed as margin>

## Timeline (UTC)

| Time | Event |
|---|---|
| | Incident begins |
| | Detected |
| | Mitigated |
| | Resolved |

## Supporting information

<Links to dashboards, logs, the alert that fired (or should have), related
postmortems, the diff/deploy that introduced the root cause.>
```
