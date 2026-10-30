---
description: Convene the Veche council
argument-hint: "<the decision, one sentence>"
disable-model-invocation: true
---
Convene the council on: $ARGUMENTS, using `idea-critic`'s `scripts/veche.py` (read its `references/council.md`).
If $ARGUMENTS is empty, ask for the one decision first. This makes paid model calls (up to 12), so convene only for a
high-stakes, hard-to-undo call.
Before running it, ask the user three things in plain words, one at a time, and wait for each answer:

1. How bad is it if this goes wrong: low, medium or high? (`--stakes`)
2. Can it be undone cheaply, or is it a one-way door: easy or hard? (`--reversibility`)
3. What should the options be judged on, and how much does each matter? For example impact 3, cost 2, risk 3.
   (`--criteria name:weight,...`.) Whenever criteria are given, collect or derive at least two options, the claim
   itself among them, each as an `--option` (a short name such as `ship`, no spaces); "do-nothing" is added for them. veche.py refuses criteria without options.

Then run `veche.py` with those flags, the decision as `--claim`, its strongest version (`--steelman`), `--twin`,
`--max-calls 12`, and `--cmd` set as in the example run in `references/council.md` (a command that reads the prompt on stdin and prints
the answer). If it prints `NOT_CONVENED`, say so and fall back to the inline `idea-critic` hats. Show the decision,
kill criteria, leading metric and review date.
