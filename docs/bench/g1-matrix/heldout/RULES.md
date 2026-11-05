# G1 held-out sets for the (a) detectors (API1, API3, API5, API10): rules

Read this before authoring, running or auditing a held-out set, or before counting an (a) label for API1, API3, API5 or API10.

BLUF: no (a) label for these four items counts until its detector has been run on a held-out set of at least 30 cases and an auditor on a different model has accepted it. Each set is written by an author who never sees the detector, from a seed published here before authoring starts. Kill rules, by 2026-11-19: a detector with precision below 0.7 is dropped, and any audit rejection among the four labels stops the plan for a re-plan. These rules are committed before any held-out case exists.

## Seed (all an author sees)
- These rules.
- The OWASP API Security Top 10:2023 page for its item.
- Its item's scope line from the table below. This says what the detector claims to cover. It is not how the detector works.

| Item | Scope line given to the author |
|---|---|
| API3 | Inbound mass assignment in JavaScript (Express or Koa with Mongoose, Sequelize or Prisma style models) and Python (Django, Django REST Framework, Flask with SQLAlchemy): the request body, or a dict or spread of it, is bound straight into a model create or update. |
| API5 | Express, Flask and FastAPI routes that are privileged (an admin path, a role or permission change, or a write on another user's record) and that are guarded by authentication only, with no role, permission or admin check. |
| API1 | Express, Flask, FastAPI and Django handlers that load a record by a client-supplied id (path, query or body) where a sibling handler in the same file, loading the same model or store, checks ownership: it scopes the lookup by the current user, or compares the record's owner with the current user. The handler in question does neither. A file with no ownership-checking sibling is out of scope. |
| API10 | Python (requests, httpx) and JavaScript (fetch, axios) code that calls a third-party or internal HTTP API, where a field of the response, possibly passed through a helper in another file of the same case, reaches a SQL string, a file path, an outbound URL or a shell command with no validation on the way, or where the call turns TLS certificate verification off. |

## Author
- A fresh agent in an empty directory. It sees only the seed.
- It never sees this repository, the detector's code, rules or tests, the skills, set b, set b2 or any run answers.
- One author per item, and each set is authored once.

## Cases
- 30 cases per item: 15 positives and 15 negatives.
- Each case is one to three files and 15 to 80 lines, inside the scope line's languages and frameworks. Spread the cases across them.
- Positives: exactly one in-scope flaw. Vary the shape: different ORMs, helpers, decorators, aliases and code layouts that real projects use.
- Negatives are near misses. Each has the same surface as a positive, with the flaw handled correctly: an allow-list, a role check, a scoped query or validation. At least 5 negatives handle it in a way that is not a textbook one-liner.
- No comment, name or string hints at a flaw or a fix. Banned: vuln, insecure, unsafe, safe, TODO, fixme, exploit, flaw, IDOR, BOLA, OWASP and any API label.
- Names are fictional (Acme, example.com).
- `cases.json` lists each case's id, kind, language, framework and, for a positive, the truth file and line.

## Run and score (deterministic, no model calls)
- The detector runs once per set, at a commit hash recorded with the result. Its code is frozen before the set is first read, and it is never tuned on the set.
- A positive is a true positive when the detector reports the truth file within 3 lines of the truth line. Any other report in a positive case, and every report in a negative case, is a false positive.
- Report precision (true positives over all reports), recall (true positives over 15) and the cases behind each number.
- Kill: a precision below 0.7 drops the detector. A low recall does not drop it, but the recall and the uncovered shapes are stated beside the label.

## Audit (different model)
- The auditor runs on a model of a different vendor than the detector's author, the set's author and the coordinator. It sees the detector, these rules, the set and the scored result.
- It answers one question per item: does this detector detect the item's class within its stated scope, well enough to earn status (a)? It answers ACCEPT or REJECT, with reasons.
- Any REJECT among the four stops the plan for a re-plan. It is not argued down.
- The audit sees only public, fictional material: the set, the detector and these rules.

## Disclosure
The coordinator who wrote these rules knows the detectors. The scope lines describe claims, not mechanisms, but a scope line can still steer an author toward shapes the detector handles. The audit is the check on that.
