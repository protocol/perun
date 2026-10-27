# Held-out scoring: sast-sca-heldout1-1027

Measure-only scoring of the preregistered blind fixture (20 vulnerable items, 20 decoys). Fixture SHA256 sums were verified before scanning (all 6 OK). No rules or fixture files were edited after seeing results. The bundled taint rules were tuned on the earlier 1027 set; this corpus is the held-out check, and it is a single small corpus authored once.

Arms (semgrep 1.182.0, `--metrics=off`, scanning `py/` and `js/`):
- A: `--config p/default` (registry rules fetched live and not pinned; re-scans may differ, so reproduce from `raw/semgrep-A.json`).
- B: bundled `templates/semgrep-taint/{py,js}.yml` at commit c1591ba9c only.
- C: B and p/default together.

Matching rule: a finding counts for an item when the file matches and the finding's start line equals the labelled sink line. A hit on a decoy is an FP; a row that maps to no item is also an FP (the 1027 `run.py` counts unmapped rows the same way, but it used function-span matching; this fixture labels single sink lines, so exact-line is the analog). A line tolerance of 2 is reported as a sensitivity check in `results.json` only.

| arm | rows | TP | FP | FN | FP breakdown |
|---|---|---|---|---|---|
| A p/default | 51 | 15 | 14 | 5 | 6 decoys + 8 unmapped rows |
| B bundled | 19 | 13 | 6 | 7 | 3 decoys + 3 unmapped rows |
| C B + p/default | 70 | 19 | 19 | 1 | 8 decoys + 11 unmapped rows |

Per class, TP/FP/FN (FP here counts decoy hits only; unmapped rows are not attributed to a class):

| class | A | B | C |
|---|---|---|---|
| cmdi | 4/1/0 | 3/0/1 | 4/1/0 |
| open-redirect | 2/0/0 | 2/1/0 | 2/1/0 |
| path-traversal | 2/1/0 | 1/0/1 | 2/1/0 |
| sqli | 1/1/3 | 4/0/0 | 4/1/0 |
| ssrf | 1/1/1 | 2/2/0 | 2/2/0 |
| unsafe-deserialize | 3/0/0 | 0/0/3 | 3/0/0 |
| xss | 2/2/1 | 1/0/2 | 2/2/1 |

Caveats: small n (20 vulnerable, 20 decoys), so differences of one or two items are not significant. Many unmapped rows may be genuine but unlabelled findings (for example tainted caller lines of the cross-file items, which the fixture README says are not separately labelled); they are counted as FP by the stated rule, which penalises every arm. Bundled rules gave no coverage of unsafe-deserialize on this corpus. Reproduce scoring with `python3 -I score.py` (no network); the scans themselves need semgrep.dev for arms A and C.

Files: `raw/semgrep-{A,B,C}.json`, `results.json`, `score.py`.

## Second run: post-code-review rules

Label: post-code-review rules; rule author never saw held-out; held-out was scored once before on pre-review rules (b35737a24). The tables above are that first, pre-review run and are kept unchanged.

Rules: `templates/semgrep-taint/` at commit d9e6fbfbb. Same fixture, same matcher. Arm B-post is the bundled rules only (`raw/semgrep-B-post.json`). Arm C-post is the union of B-post and the saved p/default output from the first run (`raw/semgrep-A.json`, reused so registry drift cannot change it), deduplicated by path, line and rule id (`raw/semgrep-C-post.json`).

| arm | rows | TP | FP | FN | FP breakdown |
|---|---|---|---|---|---|
| B pre-review | 19 | 13 | 6 | 7 | 3 decoys + 3 unmapped |
| B-post | 22 | 14 | 8 | 6 | 4 decoys + 4 unmapped |
| C pre-review | 70 | 19 | 19 | 1 | 8 decoys + 11 unmapped |
| C-post | 73 | 19 | 21 | 1 | 9 decoys + 12 unmapped |

Change: B gains one TP (a path-traversal item) and adds two FP (one more decoy hit, D05, and one more unmapped row); C gains no TP and adds two FP. The remaining B misses are V07, V08, V09, V17, V19 and V20; all three unsafe-deserialize items are still missed. Differences of one item on n=20 are not significant. Because this is a second look at the same held-out set, treat it as less blind than the first run. Per-class numbers are in `results.json`.
