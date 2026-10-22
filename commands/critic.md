---
description: Run the idea-critic on a claim
argument-hint: "<claim, plan, or path to the artifact>"
disable-model-invocation: true
---
Run the `idea-critic` skill on: $ARGUMENTS. If nothing was given, ask for the one claim or artifact to attack.
Follow its method and hats, and return its verdict (HOLD, REVISE or PASS_TO_USER) with the kill criteria. Do not
rewrite the artifact; report what would have to be true for it to hold.
