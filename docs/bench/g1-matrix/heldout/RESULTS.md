# G1 held-out results (API3, API5)

Read this before citing an (a) label for API3 or API5, or before planning a second API5 detector.

BLUF: API3's detector passes the precision bar narrowly: precision 0.727 (8 of 11 reports), recall 0.533 (8 of 15). It keeps (a), with the uncovered shapes stated below, until the different-vendor audit runs. API5's first detector fails: precision 0.55 (11 of 20 reports), recall 0.733. Under `RULES.md` it is dropped. Each set ran once, under `RULES.md` unchanged.

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
