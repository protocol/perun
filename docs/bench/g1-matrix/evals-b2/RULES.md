# G1 blind eval set b2 (API1, API10): authoring rules

Read this before authoring, checking or scoring `evals-b2`, or before giving API1 or API10 a G1 status from it.

BLUF: these rules are committed before any b2 fixture exists. b2 replaces the burned set b for API1 and API10 only. One ablation is run under `../ABLATION.md`, with no re-run. If an item fails, its fallback is a narrow-scope (a) detector, not (c).

## Why b2 exists
Run 1 (see `../ABLATION.md`, "Result (run 1)") showed that single-file textbook cases are found without the guided step. b2 tests whether the step matters on realistic code. The steps are not edited.

## Author
- A fresh agent working in an empty directory.
- It sees only these rules and the OWASP API Security Top 10:2023 pages for API1 and API10.
- It never sees this repository, the skills, the guided step text, set b or the run 1 answers.

## Cases
- For each item: 3 positives and 2 negatives.
- Each case is a small app of 3 to 6 files and 60 to 200 lines, in a common web framework. Across the 10 cases, use at least 3 languages.
- API1 positives: authorization is split between middleware or helpers and the handlers. A sibling handler in the same app does the ownership check correctly, and exactly one handler that reaches an object by a client-supplied id does not.
- API10 positives: data from a third-party or internal upstream API passes through a helper in one file and reaches a sink in another without enough checking. Examples: an unvalidated field used in a query, path or URL; redirects followed blindly; TLS verification turned off; no timeout or size bound. One flaw per case.
- Negatives look like the positives but are clean on every API class: authorization, limits, timeouts, size bounds, TLS and validation.
- No comment, name or string hints at a flaw. Words like vuln, insecure, unsafe, TODO, IDOR, BOLA and the OWASP labels are banned.
- Names are fictional (Acme, example.com).
- Disclosure: the coordinator who wrote these rules knows the step text. The case shapes above follow common real-world patterns: one endpoint forgets a check its siblings make, and upstream data crosses a file boundary. They may still favor the step, so a (b) from b2 is a claim about these shapes only.

## Truth and checks
- `evals.json` records each case's item and kind. For a positive it also records the single truth file and line.
- A second fresh agent, shown only the fixtures and the API1 to API10 titles, lists every API-class issue it sees.
- The coordinator may change a fixture only to remove a flaw of another class that this check finds, or a flaw in a negative. A truth line never moves, and every such edit is logged in the README.
- After that, the fixtures are frozen by sha256 in `../ABLATION.md` before any scored call.

## Run
- The protocol is `../ABLATION.md` unchanged: stripped arm first, the stop rule, majority-of-3 confirmation, file and class scoring, model `sonnet`, cap $15 and quota below 0.8.
- Both steps stay at the frozen blob hashes.
- One attempt.
- Kill date: 2026-11-19.
