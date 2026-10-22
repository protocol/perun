---
description: Turn an idea into a one-pager
argument-hint: "<the idea, in your own words>"
disable-model-invocation: true
---
Shape this idea into a one-pager: $ARGUMENTS. If it is empty, ask for the idea first. Build nothing and write no file
until the user confirms.

1. Ask one question per turn, the one whose answer most changes the brief (who has the problem, what hurts now, what
   done looks like). Stop asking when you could state the claim in one line.
2. Offer 2 or 3 directions, each with the belief it depends on and a one-line trade-off. Recommend one. Let the
   user pick or change it.
3. Draft the brief in the shape of `agentic-delivery`'s `references/template-onepager.md`.
4. Run the `idea-critic` skill on the draft and fold its HOLD/REVISE points in before showing it.
5. Show the brief and ask to save it. Only on a yes, write it to `docs/ideas/<short-name>.md`, where `<short-name>` is
   lowercase letters, digits and hyphens only. If that file already exists, ask before replacing it, or pick a new name.
