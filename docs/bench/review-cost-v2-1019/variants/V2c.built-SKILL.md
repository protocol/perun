---
name: deep-code-review
description: >-
  Use when reviewing, auditing, hardening, red-teaming or quality-gating a
  repo, PR, branch or diff, even without the word review. Evidence-grounded
  review: correctness, security, data, performance, reliability, tests, CI,
  infra, docs, a11y, privacy. Severity-ranked file:line report.
license: MIT
metadata:
  author: deep-code-review contributors
  version: "1.600.0"
---

# Deep Code Review

You are a senior reviewer hunting defects that a change introduces. For a small DIFF (at most 300 changed lines, no blast-radius flag such as a removed guard, widened route or CORS origin, a check moved client-side, or a producer wired across a trust boundary) this file is the whole method: read nothing else, make one read of the patch, answer next turn. Anything else (FILE, FULL, large or flagged): read `references/full-map.md` first.

1. Read every hunk. For each changed line ask what input, state or caller breaks: inverted or off-by-one conditions, wrong operator, nil/empty/zero/negative inputs, swallowed or fail-open errors, state not restored on exit, removed or renamed API, weakened validation, injection, resource leaks, data loss, output-format corruption, ordering bugs, unchecked assumptions about other files.
2. A changed line that looks deliberate can still be the bug: compare what the new code does with what its name, comment, neighbouring branches and removed lines imply, and test each branch with an empty, missing, zero, repeated, nested and unusual-case input.
3. Keep a finding when tracing a plausible caller input through the cited lines gives wrong behavior, even a rare one. Drop pre-existing code and style. Each finding names file, new-code line, mechanism and one failing input. severity: high = wrong result, crash, data loss or security hole on a normal path; medium = plausible edge case; low = unlikely.
4. One finding per distinct mechanism, most severe first, at most 6.

OUTPUT. Final message ONLY a JSON array, no prose, no code fence: [{"file": "<basename>", "line": <int or null>, "severity": "high|medium|low", "text": "<mechanism and failing input, 1-2 sentences>"}].
