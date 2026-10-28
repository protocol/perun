# Veche: the decision council (`scripts/veche.py`)

**Read this when** a decision is high-stakes AND hard to reverse, and one inline pass is too
weak: you want independent seats (optionally on different models), criteria fixed before
scoring, a mechanical aggregate, the evil twin's dissent and a closing decision record.
Named for the assembly that decided major matters; it pairs with Veles (the evil twin) and
Perun. `scripts/council.py` is a thin shim that forwards to `veche.py`, so old commands work.

## When to convene

Only for high stakes or hard reversibility (one-way door). Declare both,
`--stakes low|medium|high` and `--reversibility easy|hard`: if neither is high/hard the
script prints `NOT_CONVENED` (exit 4) and makes no call; the inline hats suffice. Declare
neither and it convenes (legacy behavior), so declare them.

## The practices, and the flag that enforces each

| Practice | Enforced by |
|---|---|
| Independent first round: every seat answers before seeing any other | each first-round prompt holds only its own lens, the claim and the packet; the critique round shows others' answers only after, anonymized |
| Decorrelated seats | `--lenses cpo,cto,cfo,ciso,user-advocate` (files in `scripts/lenses/`, editable); repeat `--cmd` so seat *i* runs on cmd *i* mod N (different models); default is the three hats |
| Criteria and weights fixed before scoring | `--criteria impact:3,cost:2`, `--option <name>` (repeat; include the claim; `do-nothing` is always added). Weights are normalized and printed to every seat; seats cannot change them |
| The evil twin argues the strongest dissent | `--twin`: after the decision, one call (`lenses/evil-twin.txt`) writes a pre-mortem and the strongest case against it; kept in `minority_report` with the dissenting seats' answers verbatim |
| Pre-mortem | every seat answers `premortem`, `kill_criterion`, `leading_metric` (recorded in `premortems`), then the twin's |
| Deterministic aggregate; the chair breaks ties | decision = highest weighted mean of seat scores (0-5 per option and criterion); a tie goes to `--chair`'s own top option, then to option order (`do-nothing` first). The verdict tally ties go to the chair, else `HOLD` > `REVISE` > `PASS_TO_USER` |
| Output: decision, kill criteria, metric, review date | record keys `decision`, `kill_criteria`, `leading_metric`, `review_date` (`--review-date`, else today + `--review-days`, default 30). A closer no seat supplied is `UNVERIFIED`, never invented |
| Convene only when it matters | the gate above |

## Run

```text
python3 scripts/veche.py --cmd "claude -p --strict-mcp-config" \
  --claim "<one sentence>" --steelman "<best version>" --packet evidence.txt --root . \
  --lenses cpo,cto,cfo,ciso,user-advocate --option "<the claim>" --option "<alternative>" \
  --criteria impact:3,cost:2,risk:3,reversibility:2 --chair cpo --twin \
  --stakes high --reversibility hard
```

- `--cmd` reads the prompt on stdin and prints the answer. Without `--lenses` it is solo-3: one cmd, the three hats.
- The packet is shown with numbered lines and its path under `--root`, so a model with no file tools
  can still cite `path:line`; keep the packet under `--root`.
- Seats answer independently. The critique round runs only when verdicts differ, with answers shuffled
  and relabelled A, B, C... (seeded, recorded). A seat changes its verdict only if its critique carries an evidenced attack.
- Claims and attacks need `path:line` plus a short verbatim `quote`. Verified = the file is under `--root`
  (no absolute path, `..` or symlink), the line is in range, and the quote appears within 3 lines of it
  (whitespace-normalized). Exists but no matching quote, or a URL: `cited_unverified`, no confidence credit.
  Unusable citations: `unsupported_claims`; bad attacks: `voided_objections`.
- Critique shows other answers in fenced blocks with a random per-run delimiter, every line prefixed,
  marked as data. With `--option`, a seat whose scores are missing or outside 0-5 is dropped like an
  unparseable one (listed in `dropped`, lowers confidence); fewer than 2 usable seats is `COULD_NOT_DECIDE`.
- `verdict` gates the claim (`owner-request` + `HOLD` becomes `REVISE`); a `do-nothing` decision turns
  `PASS_TO_USER` into `REVISE` (the claim lost to the status quo). `confidence` = (top votes / n) x (mean
  verified-claim share) x (n / seats), never self-reported.
- `--max-calls` (12), `--max-chars` (200000), `--max-seconds` (600 total) and `--timeout` (120s per call) are
  checked before each call. Any cap hit, non-zero exit, timeout or unparseable answer yields
  `COULD_NOT_DECIDE` (exit 3), never a guessed verdict. A timed-out command's grandchildren may outlive
  it, so use a cmd that exits cleanly. `--dry-run` prints planned calls.
- Validate: `scripts/validate_verdict.py --file record.json` accepts the record (it has `tally`),
  `COULD_NOT_DECIDE` and `NOT_CONVENED` with a `reason`, and a record with a `decision` only when it also
  carries `kill_criteria`, `leading_metric` and an ISO `review_date`.

## Timebox, default and blocking alarm

A council must never stall delivery. Any `COULD_NOT_DECIDE` (cap, timeout, too few seats) adds
`default_action`: `proceed` when `--reversibility easy` (take the reversible default, revisit at the review
date), else `hold` (one-way door or undeclared: hold only that item; unrelated work continues). The record
also gets `blocking_alarm: true` and a stderr line `COUNCIL_BLOCKING_WORK ...`; the same alarm fires on a
decided council slower than `--alarm-s` (300). Bound the wait with `--max-seconds`. The delivery lead acts
on `default_action` at once; a council verdict is never a reason to pause unrelated trains.

Seats of the first round, and of the critique round, run in parallel (caps are charged atomically, so
`--max-calls` and `--max-chars` still hold); wall time is about the slowest seat per round plus the serial twin
call, and the record reports `cost.round1_s`. `--timeout` bounds each seat: a timed-out seat fails the round,
which yields the `default_action` above. A malformed `--criteria` error states the `name:weight` format.

## Peer ranking and external councils

When the critique round runs, each seat also ranks the other (anonymized, lens names masked) answers best
first; valid rankings are Borda-aggregated into `peer_ranking` (lens to mean points, informational: the
verdict still comes from the tally and evidenced attacks). There is no separate adapter: any other council
can be a seat or the whole panel through the existing `--cmd`, a script that reads the prompt on stdin and
prints the JSON contract. A seat that fails (cap, timeout, cmd exit) is dropped and lowers confidence; a
failed critique call or twin keeps the round-1 verdict. Versus the fetched sources (`docs/standards-index.md`):

| | llm-council | Du et al. debate | Mixture-of-Agents | Veche |
|---|---|---|---|---|
| Anonymized peer review | yes | no | no | yes, plus Borda `peer_ranking` |
| Aggregation | README silent | consensus | aggregator LLM | deterministic tally and weighted criteria |
| Chairman synthesis | yes | no | yes | no (tie-break only, by design) |
| Evidence rule | no | no | no | verified `path:line` quotes |
| Timebox and default | no | no | no | `default_action`, `COUNCIL_BLOCKING_WORK` |
| Parallel seats | not stated | not stated | layered | yes, capped atomically |

## Kill criterion

Debate-style councils often fail to beat plain self-consistency
(`docs/standards-index.md`, "Should we be going MAD?"). Keep the council only if,
at equal call budget, it beats self-consistency-3 (same cmd, three samples, vote)
on the bench by a margin that survives a bootstrap over TEST cases. Otherwise it
stays opt-in or is removed.

Measured 2026-10-13 (29 labelled pass/block cases from `evals/`, one mid-tier model with file-read
tools, the three-hat council): council, self-consistency-3 and a single call all scored 29/29, so the set
cannot separate them; the council cost about twice self-consistency-3 (critique ran on 7 cases). No accuracy
advantage is shown. It stays opt-in: use it for the audit trail (verified citations, kept dissent, the
fixed criteria and the minority report) or mixed models, not for accuracy, until a harder set says
otherwise. The seats, scoring, twin and convene gate are unit-tested (`scripts/test_veche.py`), not measured
for accuracy; the tool-less path is untested for accuracy.
