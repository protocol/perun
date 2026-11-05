# G1 pilot: blind evals for the status (b) items

Read this when you score a guided step for API1, API3, API5 or API10 (OWASP API Security Top 10:2023), or audit how these evals were made.

BLUF: 12 fixtures, 2 positives and 1 negative per item, written before any guided step for these items exists. `python3 docs/bench/g1-matrix/evals-b/check.py` checks their shape.

How they were made:
- Author: a fresh agent, working in an empty directory. It was shown only the item list and the OWASP API Security Top 10:2023 pages (the fetched URLs are in `evals.json` and `docs/standards-index.md`). It was not shown this repository, the skills, `DENOMINATORS.md` or any earlier result.
- Coordinator edits after authoring, before any guided step was written. They removed flaws of another class and did not move any truth line: `api5-a/main.go:12` now looks the session up instead of accepting any non-empty header (a missing-authentication flaw), and `api10-a/sync.py` and `api10-c/sync.js` now require an admin on the sync route (no authentication on a write route, and the negative must be clean).

Scoring: a positive is a hit when the report names the item's flaw in the truth file; each positive holds only that one flaw, so file plus class is enough and line numbers are context. A negative passes when the report names no flaw of the item's class. Ablation compares the same fixtures with the guided step present and removed.
