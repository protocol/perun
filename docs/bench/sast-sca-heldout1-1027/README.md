First blind held-out SAST corpus (20 planted vulnerabilities, 20 safe decoys), authored 2026-10-27 by a Claude subagent without reading any scanner, rule, scorer, review check or earlier docs/bench/sast-* content; only the secrets-heldout16 README was consulted, for format and freeze conventions. Everything is fictional (placeholders only: acme, example.com).

Files: `py/users_app.py`, `py/db_helpers.py` (Python/Flask), `js/server.js`, `js/lib/shell.js`, `js/public/widget.js` (Node/Express and browser). Classes: sqli, cmdi, path-traversal, ssrf, unsafe-deserialize, xss, open-redirect. Flows: direct, cross-function (taint built in one function, sunk in another), cross-file (sink in a helper module).

`ground-truth.json`: one row per item with `id`, `file`, `line` (1-based), `class`, `label` (`vuln` or `decoy`), `flow`. The line is the sink line. For cross-file items the vulnerable sink is the helper line (V11 `py/db_helpers.py`, V20 `js/lib/shell.js`); the tainted caller lines (the `/raw` route in `py/users_app.py`, the `/run` route in `js/server.js`) are not separately labelled. D11 and D20 are the call sites that pass a constant to those same helpers, so a scanner that flags the helper sink is correct on V11/V20 and should not be penalised for it on D11/D20 unless it flags the constant call site. Decoys use safe equivalents (parameterization, argv lists, quoting, basename, allowlists, escaping, safe loaders).

Frozen by SHA256 (`SHA256-frozen.txt`, covering all corpus files and `ground-truth.json`) and preregistered in `ledger.jsonl` before any scoring.

Scoring status: unscored at preregistration; no scanner was run and no file was executed at authoring time.
