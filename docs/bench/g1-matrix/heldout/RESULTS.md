# G1 held-out results (API1, API3, API5, API10)

Read this before citing an (a) label for API1, API3, API5 or API10, or before planning a second API5 or API10 detector.

BLUF: API3's detector passes the precision bar narrowly: precision 0.727 (8 of 11 reports), recall 0.533 (8 of 15). It keeps (a), with the uncovered shapes stated below, until the different-vendor audit runs. API5's first detector fails: precision 0.55 (11 of 20 reports), recall 0.733. Under `RULES.md` it is dropped. Each set ran once, under `RULES.md` unchanged.

Run 2: API1's detector passes with precision 1.0 (7 of 7 reports) and recall 0.467 (7 of 15). It keeps (a), pending the audit. API10's first detector fails, with precision 0.667 (2 of 3 reports) and recall 0.133, so it is dropped.

## Run
- The scorer is `score.py`, sha256 `1224864eaf779a677e267a2ab107f27cad3302cf31471fee15f2604dd6e64d42`. It was written after both sets existed, but before the coordinator read any case and before the first run, and it was not changed after scoring. It takes the detector from git at the frozen commit with `git archive` and scans each case directory once. It makes no model calls.
- API3: semgrep 1.183.0, rules `perun.js.mass-assignment` and `perun.py.mass-assignment` at `02f5d8406`. API5: `route_auth_map.py --privileged` at `00550ed93`.
- Raw rows for each case are in `api3/result.json` and `api5/result.json`, along with the sha256 of every case file.
- A diagnostic re-run (not scored) on the 7 missed API3 positives and the 3 API3 false positives found no semgrep errors, and every case file was scanned. The misses are rule misses, not parse failures. The sandbox denied semgrep's outbound calls to semgrep.dev. The scan uses local rules only, so this does not change the scan.
- After scoring, no negative was re-labelled in either direction.
- The authors' generator and check scripts are kept in `api3/author/` and `api5/author/` for provenance. They are not part of the set.

## API3 (kept, pending audit)
| | Count | Cases |
|---|---|---|
| True positives | 8 | h3-02, h3-06, h3-11, h3-15, h3-21, h3-22, h3-23, h3-26 |
| Missed positives | 7 | h3-01 (Mongoose `{ $set: patch }`, with the body passed through a helper), h3-03 and h3-19 (Prisma `data: payload` / `data: req.body`), h3-13 (Django `filter(...).update(**data)`), h3-20 (DRF serializer `exclude = (...)`), h3-27 (Flask `setattr` loop over the body), h3-28 (Django `objects.create(**data)` through an alias) |
| False positives | 3 | h3-07 (DRF `fields = "__all__"` with `extra_kwargs` marking fields read-only), h3-08 (`User(**request.get_json())` on an admin-only route), h3-30 (Sequelize `Account.update(req.body, ...)` after an ownership check) |

Uncovered shapes stated beside the label: Prisma `data:` objects, Mongo update operators, Django queryset `.update(**x)`, DRF `exclude`, and a body that reaches the model through an alias or a helper.

## API5 (first detector dropped)
| | Count | Cases |
|---|---|---|
| True positives | 11 | h5-01, h5-03, h5-04, h5-05, h5-06, h5-09, h5-12, h5-17, h5-20, h5-21, h5-29 |
| Missed positives | 4 | h5-16, h5-18, h5-19, h5-27 |
| False positives | 9 | h5-04 (a second admin route in the same file), h5-07, h5-10 (two routes behind a router-level custom guard that compares `req.user.tier`), h5-11 (FastAPI `Security(..., scopes=["admin"])`), h5-15, h5-23, h5-24, h5-30 |

Most false positives come from guard shapes the detector does not read: router-level guards, scope-based dependencies and custom predicates. A second API5 detector needs an amendment to `RULES.md`, committed before a new set is written. `h5` becomes its development set.

## Run 2 (API1, API10)
- The scorer was extended to `score.py` sha256 `bb55c8d12338a2b2b7809026ca07aec6ab8a6f4f96b3cdc2babf217b58eacc96`. The change only adds two items: `api1` and `api10`, and a shared semgrep helper that `api3` now calls. It was written after both new sets existed but before the coordinator read any of their cases. It was not changed after scoring. Before the new runs, it was re-run on the committed API3 and API5 sets, and its results matched `api3/result.json` and `api5/result.json` field for field, except the per-file hashes, which were not compared. The first scorer, sha256 `1224864e…`, is in this file's git history.
- API1: `ownership_sibling_check.py` at `6f6ff6813`. API10: semgrep 1.183.0, rules `perun.py.unsafe-api-consumption`, `perun.js.unsafe-api-consumption`, `perun.py.tls-verify-off` and `perun.js.tls-verify-off` at `25e958e3a`. Both detectors were frozen and pushed before either set was first read.
- Each set ran once, under `RULES.md` unchanged. No case was re-labelled after scoring.
- A diagnostic re-run (not scored) of both API10 semgrep files over the whole API10 set found no semgrep errors, and all 37 case files were scanned. The misses are rule misses, not parse failures. That re-run also showed other, older rules in the same files (`sqli`, `command-injection`, `path-traversal`, `ssrf`) firing on several API10 positives and negatives. Those rules are not the declared API10 detector, so they are not counted, and switching to them after seeing the set would be tuning on it.

## API1 (kept, pending audit)
Precision 1.0 (7 of 7 reports), recall 0.467 (7 of 15).

| | Count | Cases |
|---|---|---|
| True positives | 7 | e01, e02, e03, f01, a01, d01, d02 |
| Missed positives | 8 | e04 (a knex `where({ id }).first()` lookup on a `return` line), f02 and a04 (raw SQL with a bound id), f03 (a `Task.get_by_id(...)` getter), f04 (`db.session.get(Booking, booking_id)`), a02 (a `PROFILES.get(pid)` store lookup), a03 (`s.get(Order, body["order_id"])`), d03 (Django `filter(pk=request.POST[...]).first()`) |
| False positives | 0 | |

Uncovered shapes stated beside the label: raw SQL lookups, knex lookups on a `return` line, model getter methods such as `get_by_id`, `.get` on a store object, SQLAlchemy `session.get` with the id from a body or a local, and Django `filter(...).first()` on a POST field.

## API10 (first detector dropped)
Precision 0.667 (2 of 3 reports), recall 0.133 (2 of 15).

| | Count | Cases |
|---|---|---|
| True positives | 2 | p05 (a response field in a file path), p15 (`rejectUnauthorized: false`) |
| Missed positives | 13 | p01, p02 and p04 (SQL strings), p03, p07, p10 and p13 (the field passes through a helper in another file: SQL, path, URL and shell), p06 (`fs.writeFileSync` path), p08 and p09 (outbound URL), p11 and p12 (shell command, one through a `sh` wrapper), p14 (`verify=False` on a client call) |
| False positives | 1 | n05 (`fetch_assets.py` line 20) |

Nine of the 13 misses are single-file cases, so the cross-file limit explains only 4 of them. A second API10 detector needs the same amendment route as API5, committed before a new set is written. `h10` would become its development set.

## Audit plan (declared before the first audit call)
- Runner: `audit.py`, committed with this section. It builds the prompt only from committed files and records the prompt's sha256.
- Model: `Qwen3.5-397B-A17B` on the PCSS endpoint, a different vendor from every author and from the coordinator. Temperature 0, one call per item.
- A transport error or an answer with no parseable verdict may be retried once with the same prompt, and both responses are kept. Neither of those is counted as an ACCEPT.
- Order: API3 first. A REJECT on any item stops the plan for a re-plan, as `RULES.md` says. API5 is audited only after a detector for it passes its own held-out set.
- The raw prompt, response and verdict go to `api3/audit/` and are committed whatever the outcome.
