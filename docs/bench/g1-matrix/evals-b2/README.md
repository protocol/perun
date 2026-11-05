# G1 blind eval set b2 (API1, API10)

Read this before scoring with `evals-b2`, auditing its fixtures, or citing a G1 status that rests on it.

BLUF: 10 multi-file cases (3 positives and 2 negatives per item) in JavaScript, Python and Go. A fresh agent wrote them blind under `RULES.md`, which was committed before any fixture existed. A second fresh agent's class check found every positive's truth file. Only negatives were edited, to remove the flaws that check found. The fixtures are frozen by sha256 in `../ABLATION.md` ("Frozen inputs (b2)") before any scored call.

## Authoring
- Author: a fresh agent (`sonnet`) in an empty directory. It saw only `RULES.md` and the OWASP API Security Top 10:2023 pages for API1 and API10. It never saw this repository, the skills, the guided step text, set b or the run 1 answers.
- Output: `evals.json` (item, kind and, for a positive, the truth file and line) and `fixtures/<id>/` (3 to 6 files and 60 to 200 lines per case).
- Disclosure, from `RULES.md`: the coordinator knows the step text, and the case shapes (one handler skips a check its siblings make; upstream data crosses a file boundary) may favor the step. A (b) from this set is a claim about these shapes only.

## Class check and edits
The check prompt, the same for every round: system "You are a careful application security reviewer."; user = the case's files, the API1 to API10 titles, and "List every security issue in the files above that falls under any OWASP API Security Top 10:2023 class listed, including minor ones," followed by a fenced JSON list. Model `sonnet`, no tools. Raw answers are in `check/r1/`, `check/r2/` and `check/r3/`.

| Round | Cases | Cost | Plan-quota utilization | Result |
|---|---|---|---|---|
| 1 | all 10 | $0.327 | 0.46 | every positive truth file found; real flaws in all 4 negatives |
| 2 | 4 negatives | $0.117 | 0.48 | `api1-d` and `api1-e` clean; minor API10 and cross-class findings in `api10-d` and `api10-e` |
| 3 | `api10-d`, `api10-e` | $0.061 | 0.48 | no API1 or API10 finding in `api10-d`; one minor API10 finding in `api10-e` (see below) |

Round 3 was decided as the last before it ran: whatever it finds is listed under "Residual findings" and not fixed. Every edit below is in a negative. No positive and no truth line changed.

### Edits after round 1
- `api1-d/routes.py`: the list endpoint returns the same field allow-list as the detail endpoint (the check found `staff_note` exposed in the list).
- `api1-e/policy.js`: API keys come from an environment variable and are looked up in a `Map` (the check found hardcoded keys and a plain-object lookup that resolves inherited keys such as `__proto__`).
- `api1-e/projects.js`: PATCH returns 400 unless `name` is a string (the check found that a non-JSON body throws).
- `api1-e/index.js`: `x-powered-by` is disabled.
- `api10-d/app.py`: POST /sync requires an admin key, the SQLite connections are closed, and `VendorError` maps to 502 (the check found an unauthenticated sync and leaked connections).
- `api10-d/vendor.py`: the body is read in chunks under a size cap and an overall deadline, and malformed JSON or an unexpected shape raises `VendorError` (the check found that the timeout applies only per socket operation and that malformed upstream JSON is unhandled).
- `api10-d/checks.py`: booleans are rejected as prices.
- `api10-e/directory.js`: the byte cap is enforced while reading the stream, not only through Content-Length (the check found that chunked bodies bypassed the cap).
- `api10-e/server.js`: a profile whose handle differs from the requested one returns 502, a small per-IP rate limit is added, and `x-powered-by` is disabled (the check found that a mismatched upstream profile was cached under another handle, and that there was no rate limit).

### Edits after round 2
- `api10-d/checks.py`: non-dict items are skipped and the SKU pattern must match the whole string (the check found an AttributeError on non-dict items, and `$` accepting a trailing newline).
- `api10-d/catalog.py`: only items of the requested category are stored (the check found that vendor rows could overwrite other categories).
- `api10-d/vendor.py`: `requests` exceptions and `RecursionError` map to `VendorError`.
- `api10-d/app.py`: the admin key is compared as bytes, a small per-IP rate limit is added, and a non-blocking lock returns 409 while a sync runs (the check found a TypeError on non-ASCII keys, no rate limit, and concurrent syncs).
- `api10-e/directory.js`: the response must be `application/json`.
- `api10-e/sanitize.js`: control characters and `<>` are stripped from `displayName` (the check found the upstream name passed through unchanged).
- `api10-e/server.js`: concurrent misses for the same handle share one upstream fetch, the rate-limit map is bounded, and JSON responses carry `nosniff` and `no-store`.

## Residual findings (round 3, not fixed)
Round 3 found no API1 or API10 issue in `api10-d`, and one API10 issue in `api10-e`. It is left in place and disclosed here, because it could make either arm flag this negative:
- `api10-e/sanitize.js:16` (API10): Unicode bidi and format characters, quotes and ampersands in `displayName` pass through.

Other-class findings left in place: rate-limit maps reset when they exceed 10,000 keys (API4, both cases), no trust-proxy setting (API8, `api10-e`), and no global cap on concurrent upstream fetches (API4, `api10-e`). They do not affect scoring, which counts only the item's own label.
