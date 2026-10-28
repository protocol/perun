# Retrospective — G10 Learn, made real

Read this when running G10, or when a target's own incident/postmortem
practice is in scope for a review. `SKILL.md`'s G10 row is one line —
"Retrospective. Escaped gap → regression test in this repo. Reusable lesson is
generalized..." — this file is the discipline behind it: when a retrospective
is mandatory (not every bug fix), what it must contain, and the gate that
keeps an action item from quietly dying.

---

## Blameless — the principle the rest depends on

A postmortem assumes everyone involved had good intentions and acted on the
information they had at the time. Findings point at systems and processes,
never at a person: a blame culture teaches people not to bring issues to
light for fear of punishment, and you cannot "fix" a person the way you can
fix a system. State this explicitly at the top of every postmortem — it is
the reason people write the honest timeline instead of the defensible one.

## Mandatory-trigger criteria — not every bug fix

The existing "regression test first" rule already covers an ordinary bug. A
written postmortem is required when at least one of these fired:

- user-visible downtime or degradation past a stated threshold;
- any data loss;
- on-call/human intervention was required (rollback, traffic reroute, a
  manual fix);
- resolution time exceeded a stated threshold;
- the problem was found by a person, not by monitoring (a detection failure
  is itself a finding — see Detection below);
- a stakeholder asked for one anyway.

Below that bar, the existing "escaped gap → regression test" line is
sufficient; do not manufacture postmortem ceremony for a routine fix.

## Shape — the vendored template

`template-postmortem.md` in this skill's `references/` ships the full section
order: Summary, Impact (quantified — "some users noticed issues" is not
impact), Root Cause(s) (plural; list every contributing cause, don't collapse
to one for narrative neatness), Trigger (the technical event that activated
the root cause), Resolution (including what was tried and did **not** work),
Detection (how it was noticed — a missing alert that should have fired is a
finding), Action Items (owner + tracking reference required), Lessons Learned
(what went well / what went poorly / where we got lucky — don't let luck get
filed as margin), Timeline, Supporting information.

## Action-item closure — the gate that makes this more than a document

An action item with no owner or no tracking reference is not done — it is a
sentence that will be forgotten. Every item in the table carries a named owner
and a bug/issue reference; `In progress`/`Open` items are re-checked at the
next retrospective touching the same area, not left to rot. An item that is a
lesson lands as a gate, eval, or regression test proven red on the planted
defect — never only a doc line; a prose-only fix leaves it `Open`.

## Repeat-root-cause check

Before closing a postmortem, check whether its root cause matches an earlier
one. If it does and no new regression test, alert, or gate was added since the
earlier incident, the missing safeguard **is** the finding — name which
regression test, alert, or gate should have existed and did not. This is the
same "gate proven red on a planted defect" discipline this skill already
applies to code, applied to incident causes: a recurring root cause with
nothing new added between occurrences means nothing was actually learned the
first time.

Every finding that is fixed leaves one pin test, and every train runs all pin tests. Before filing a new finding, run the fingerprint duplicate check (`scripts/file_finding.py`) so a recurrence reopens the old finding instead of adding a second one.

## Cross-reference — the reliability contract this feeds

`role-coverage.md`'s Platform/DevOps/SRE lens (`deep-code-review` skill) owns
SLI/SLO/error-budget/burn-rate — multiwindow, multi-burn-rate alerting so a
fast burn pages and a slow burn tickets. A postmortem's Detection section is
where that alerting is judged after the fact: did the burn-rate alert that
should have caught this actually fire, and if not, why not.

---

## Gate, trigger, planted-defect test

- **Gate:** a postmortem exists with every section filled, every action item
  owned and tracked, and a matching-root-cause check against prior
  postmortems. **Trigger:** the mandatory criteria above — not every bug fix.
  **Owning hat:** Conductor or Release (G10 is post-hoc and cross-cutting).
- **Planted-defect test 1:** an action item with no owner and no tracking
  reference → the gate flags it.
- **Planted-defect test 2:** a second postmortem citing the same root cause as
  an earlier one, with no new regression test or gate referenced since → the
  gate flags "repeat cause, no new gate."

Replay a proposed fix for a recurring failure class against the past instances before accepting it, and key it on signals the change itself carries (touched paths, shadow or default-off wording) rather than labels, which are absent or wrong exactly when it matters.
