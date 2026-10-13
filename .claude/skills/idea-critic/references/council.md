# Council: independent multi-lens verdict (`scripts/council.py`)

**Read this when** a verdict is high-blast or irreversible and one inline pass is
too weak: you want the three hats (see SKILL.md, Hats) run as independent calls,
optionally on different models, with a mechanical tally instead of one model's
judgment.

## Run

```text
python3 scripts/council.py --cmd "claude -p --strict-mcp-config" \
  --claim "<one sentence>" --steelman "<best version>" --packet evidence.txt --root .
```

- `--cmd` reads the prompt on stdin and prints the answer; repeat it for mixed
  models (lens *i* uses cmd *i* mod N). Default is solo-3: one cmd, three lenses
  in `scripts/lenses/*.txt` (plain text, no host tool names; edit them freely).
- The packet is shown with numbered lines and its path under `--root`, so a model with no file tools
  (a bare `ollama run`, an API one-shot) can still cite `path:line`; keep the packet under `--root`.
- Lens answers are independent: no lens sees another's. The critique round runs
  only when verdicts differ, with answers shuffled and relabelled A/B/C (seeded,
  recorded). A member changes its verdict only if its critique carries an
  evidenced attack.
- Claims and attacks need `path:line` plus a short verbatim `quote`. Verified = the file is
  under `--root` (no absolute path, `..` or symlink), the line is in range, and
  the quote appears within 3 lines of it (whitespace-normalized). Exists but no
  matching quote, or a URL: `cited_unverified`, no confidence credit. Unusable
  citations: `unsupported_claims`; bad attacks (no valid citation, or target not
  another answer's label): `voided_objections`.
- Critique shows other answers in fenced blocks with a random per-run delimiter,
  every line prefixed, marked as data. One unparseable lens is dropped (listed in `dropped`, lowers confidence); fewer
  than 2 parseable answers is `COULD_NOT_DECIDE`.
- Verdict = deterministic tally; ties go to the more cautious
  (`HOLD` > `REVISE` > `PASS_TO_USER`); `owner-request` + `HOLD` becomes `REVISE`.
  `confidence` = (top votes / n) x (mean verified-claim share over the n parsed
  lenses) x (n / 3, the drop factor), never self-reported.
  Minority answers are kept verbatim in `dissent`.
- `--max-calls` (8), `--max-chars` (200000), `--max-seconds` (600 total) and
  `--timeout` (120s per call) are checked before each call; any internal error
  also maps to `COULD_NOT_DECIDE`. A timed-out command's grandchildren may
  outlive it, so use a cmd that exits cleanly. Any cap hit, non-zero exit, timeout or unparseable
  answer yields `COULD_NOT_DECIDE` (exit 3), never a guessed verdict.
  `--dry-run` prints planned calls.
- Validate: `scripts/validate_verdict.py --file record.json` accepts the council
  record (it has `tally`) and `COULD_NOT_DECIDE` with a `reason`.

## Kill criterion

Debate-style councils often fail to beat plain self-consistency
(`docs/standards-index.md`, "Should we be going MAD?"). Keep the council only if,
at equal call budget, it beats self-consistency-3 (same cmd, three samples, vote)
on the bench by a margin that survives a bootstrap over TEST cases. Otherwise it
stays opt-in or is removed.

Measured 2026-10-13 (29 labelled pass/block cases from `evals/`, one mid-tier model with file-read
tools): council, self-consistency-3 and a single call all scored 29/29, so the set cannot separate
them; the council cost about twice self-consistency-3 (critique ran on 7 cases). No accuracy
advantage is shown. It stays opt-in: use it for the audit trail (verified citations, kept dissent)
or mixed models, not for accuracy, until a harder set says otherwise.
