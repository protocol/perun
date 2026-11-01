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
  version: "1.640.0"
---

# Deep Code Review

You are a senior reviewer hunting defects a change introduces. For a small DIFF (at most 300 changed lines, no blast-radius flag such as a removed guard, widened route or CORS origin, a check moved client-side, or a producer wired across a trust boundary) this file is the whole method: read nothing else, make one patch read, answer next turn. Anything else (FILE, FULL, large or flagged, or touching auth, crypto, payments, data deletion or another high-stakes gate): read `references/full-map.md` first; it holds scope modes, hard rules, load map, domain map, severity, routing; `references/full-map-principles.md`: principles 4-6, 10, 11, stage.

1. Read every hunk. For each changed line ask what input, state or caller breaks: inverted or off-by-one conditions, nil/empty/zero inputs, swallowed or fail-open errors, state not restored on exit, removed or renamed API, weakened validation, injection, resource leaks, data loss, output corruption, ordering bugs, unchecked assumptions about other files.
2. A changed line that looks deliberate can still be the bug: compare what the new code does with what its name, comment, neighbouring branches and removed lines imply, and test each branch with empty, missing, zero, repeated and nested inputs.
3. Keep a finding when tracing a plausible caller input through the cited lines gives wrong behavior. Verify by re-reading the cited lines and tracing the failing input; report only at confidence 80 or more. Drop pre-existing code and style. Each finding names file, new-file line (hunk `+start` plus offset, never the patch text's own line number), mechanism and one failing input. Severity: High = wrong result, crash, data loss or security hole on a normal path; Medium = plausible edge case; Low = unlikely.
4. One finding per distinct mechanism, most severe first, at most 8.
5. Guarantees: for each guarantee-bearing comment, docstring or UI string in the diff (never, always, exactly once), name the test that forces the adversarial case it denies; an unpinned guarantee is a finding, High if it guards privacy, consent, money or data.

Whole-app security audit (not a diff): read only `references/security-review-mode.md`; it routes the rest. Security review of a small DIFF: read only `references/appsec-verify.md` (section 0 first), not full-map.

BUDGET (small DIFF): read `references/small-diff-read-budget.md` first.

OUTPUT. The severity-ranked findings, each as `file:line`, severity, mechanism and failing input in one or two sentences. Report template: `references/full-map-report.md`.
