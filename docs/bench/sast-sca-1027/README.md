# SAST and SCA bench: raw scanners vs Perun's deterministic triage (2026-10-27)

Bottom line: on this fixture Perun's deterministic layer does not find anything the raw scanners miss, and it does
not remove any false positive by itself. Its SAST arm reports 0 FP only because it demotes every row to
`unverified` (a question, not a finding); that is not a precision gain. Its SCA threshold filters out lower-severity
advisories, trading recall for fewer rows.
The precision gain the design claims comes from the LLM verify step, which was **not run here (no spend)**; that
step is an upper bound left untested. Secrets are out of scope (see `docs/bench/secrets-heldout*`).

## Fixture (frozen before any scanner ran)

Fictional code only (`acme`, `example.com`) in `fixture/`: Python (`py/`), JavaScript (`js/server.js`), and two
dependency files (`requirements.txt`, `js/package-lock.json`). `ground-truth.json` (written by `build_truth.py`) and
`SHA256-frozen.txt` (fixture, ground truth and `build_truth.py`) were frozen by the author in a single commit with the
fixture, before the first scan; `run.py` aborts if any frozen file's hash drifts. This is self-attested, not
externally timestamped.

- 13 vulnerable code blocks: 2 SQLi + 1 JS SQLi, 3 command injection, 2 path traversal, 2 SSRF, 2 unsafe deserialize, 1 JS `eval`. Items are function blocks (`lines` = block span); a finding counts if its line falls in the span.
- 14 decoy code blocks (parameterized queries, constant shell/argv, allowlisted paths and hosts, `safe_load`, `JSON.parse`).
- 4 vulnerable pinned dependencies (pyyaml 5.3, jinja2 2.11.2, lodash 4.17.15, minimist 1.2.0) and 4 intended-patched decoys.
- Scoring: TP = vulnerable item flagged; FN = vulnerable item not flagged; FP = decoy item flagged plus any finding row that maps to no item (counted once each).

## Results (`results.json`, produced by `python3 run.py`)

| Arm | TP | FP | FN | Notes |
|---|---|---|---|---|
| semgrep 1.182.0 `--config p/default`, raw (16 rows) | 8 | 3 | 5 | FP: `count_orders` (constant concat), `/legal` (allowlisted path), 1 header-line CSRF row outside any block. Missed: JS SQLi `/user`, JS SSRF `/proxy`, `ping_host`, `read_report`, `fetch_remote` |
| Perun `security_verify.py` triage over the semgrep rows (FN by construction) | 0 | 0 | 13 | All 16 rows `unverified`: semgrep gave no taint trace, so no `path:line` source (`semgrep_rows_with_dataflow_trace` = 0 of 16 in `results.json`). They stay as questions for the verify step; nothing is asserted. The 16 leads are the same set as the raw arm |
| OSV querybatch, raw (8 packages) | 4 | 2 | 0 | FP: `requests==2.32.4`, `js-yaml==4.1.0` (see label caveat) |
| Perun `supply_chain_check.sh --fail-on high` (simulated threshold) | 4 | 2 | 0 | Filters out moderate-only advisories; none of the 4 vulnerable packages is moderate-only, so same packages as raw |
| Perun `supply_chain_check.sh --fail-on critical` (simulated threshold) | 3 | 1 | 1 | Filters out lodash (high only). Keeps jinja2 and requests only via PYSEC "unknown" advisories (fails closed); the requests keep is the FP |

Label caveat: the two SCA "FP" decoys (`requests==2.32.4`, `js-yaml==4.1.0`) were labelled patched from memory and
OSV today lists real advisories for both (`raw/supply_chain_low.txt`). The frozen labels were not edited after the scan;
the computed `results_relabeled` block in `results.json` drops both from scoring: OSV raw 4/0/0, `--fail-on high` 4/0/0, `--fail-on critical` 3/0/1.
OSV data moves daily, so re-running later can change SCA numbers; the saved raw output is what was scored.

## Not run or degraded

- LLM verify step: not run, no paid model calls. Upper bound only: verify can promote or drop the 16 semgrep leads, so it could cut the 3 FP, but it cannot recover the 5 FN, which no scanner row points at.
- osv-scanner 2.7.0 CLI: failed in this sandbox (Go TLS `x509: OSStatus -26276`, plus `requirements.txt` resolution via a blocked host; `raw/osv-cli-failed.json`). The raw arm is the OSV `querybatch` API with the 8 pinned packages (`raw/osv-query.json`, `raw/osv-querybatch.json`), the same fallback `scripts/test-scanner-sandbox-fallback.sh` exercises; `raw/supply_chain_{low,high,critical}.txt` are real `supply_chain_check.sh --online --fail-on <level>` runs (itself running that fallback; each exits 1). The script prints every advisory at every level and only sets the exit code, so the `--fail-on` rows above apply its threshold rule (unknown fails closed) in `run.py` to the saved output: marked "simulated".
- `review_checks.sh`: not run. The sandbox denied the command that built a throwaway git repo for it, and the stop-on-denial rule applied. Without a local `.semgrep.yml` it would skip semgrep by design (it never uses registry configs), so it does not apply to the `p/default` arm.
- The `p/default` rule set is fetched live and was not pinned; no rule hash or version is recorded. Re-scans may differ, so reproduction is guaranteed only from the saved `raw/semgrep.json`.
- semgrep ran with `HOME` and `SEMGREP_USER_HOME` set to a temp dir, `--metrics=off`; it fetched the `p/default` registry rules (network to semgrep.dev only). No external host was scanned.

## Reproduce

```
cd docs/bench/sast-sca-1027
python3 run.py        # re-score saved raw output; checks fixture hashes
# re-scan:
(cd fixture && HOME=$TMPDIR SEMGREP_USER_HOME=$TMPDIR semgrep --config p/default --metrics=off --json -o ../raw/semgrep.json .)
curl -X POST -H 'content-type: application/json' --data @raw/osv-query.json https://api.osv.dev/v1/querybatch -o raw/osv-querybatch.json
bash ../../../.claude/skills/deep-code-review/scripts/supply_chain_check.sh --online --fail-on high fixture > raw/supply_chain_high.txt   # likewise critical, low
```
