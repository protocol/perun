# Perun security "ready" bar v3 (2026-11-03; pre-registered before any measurement)

Owner ask (11-03): Perun must audit, review and investigate a whole project and confirm it follows security best
practice and standards (dependencies current, data/API calls secured), or name the fixes. Process: a decision
council of 5 seats picked the layered option over the other 3 candidates and do-nothing (4/4 REVISE, score 3.80 vs
3.52/3.48/2.52). Three independent evil-twin passes on the v2 draft (Sonnet, Haiku, Opus) then raised 24 kills.
One Opus re-attack on v3 raised 8 more. Each of the 32 kills changed the bar or has a written rebuttal. The v3
re-attack's folds have not been re-attacked.

**Meaning.** Perun never says "secure". Ready means Perun can audit a whole project against named standards, back
each pass with a check that ran, list what it did not check, and produce fixes that are validated without gaming.

**Rules.**
- Thresholds are fixed now. Changing one after any result restarts that gate on a fresh set.
- Every fixture is authored by a blind lane that never reads the skill, the detectors or the rival prompt.
- An "unknown" or "not checked" verdict on a seeded positive counts as a miss.
- Rates are reported with a Wilson 95% interval. A rate passes only if both hold:
  - the point estimate is ≥ the threshold;
  - the Wilson lower bound is ≥ the threshold − 0.20.
  For example, 9/12 at a 0.75 threshold fails, and 11/12 passes.
- Each fixed set gets one scored attempt. The commit sha is logged before the run.
  - A failed attempt needs a fresh blind set.
  - The G3 holdout is burned after its one scored use.
  - Re-measures for tuning run on tune sets only.
- A finding that isn't in a truth set is checked against the code by the adjudicator. If it's verified, it counts as
  a true positive and is added to the truth set.

**Stages.** Ready = every gate passes, then the confirmation run (C) passes.
- S1: G0, G3 (re-measure), G5
- S2: G1, G6, G9, G10
- S3: G2, G4, G7
- Then C

## Gates

**G0 Report contract (honesty).**
- Each whole-project report has:
  - a per-standard table (the G1 lists), with pass / fail / not-checked per item;
  - a NOT CHECKED list;
  - a static-vs-runtime section naming what needs a running system (deployed config, WAF, runtime authz, vault,
    infra outside the repo);
  - a dependency section.
- A "pass" needs a check that ran: a tool row, or a guided step with a G1 eval behind it. Anything else is
  "not checked".
- A guided-step pass also needs evidence from this project: the files it examined and a quoted negative (the code
  that shows the risk is handled). The linter rejects a guided pass without both. False passes are also sampled from
  guided rows on apps seeded for those exact items.
- An item whose tool is in NOT RUN is "not checked".
- A deterministic linter fails a report that:
  - claims safety in any phrase on a published list (seeded paraphrases are tested);
  - has an unstatused item;
  - cites a path or line that doesn't exist;
  - leaves more than 40% of (a)/(b) items "not checked" without a NOT RUN reason.
- Pass:
  - the linter passes on 100% of G2, G3, G6 and G9 reports;
  - its seeded negative tests fail;
  - false passes ≤ 1 of 30 "pass" rows sampled from reports on seeded-positive apps.

**G1 Standards matrix.**
- The lists:
  - ASVS 5.0 L2
  - Top 10:2025
  - API Top 10:2023
  - CWE Top 25 (2025)
  - LLM Top 10 2025
  - Agentic Top 10 2026
- Every item gets one status:
  - **(a)** A deterministic detector with seeded positive and negative tests.
  - **(b)** A guided review step with a blind-authored eval: at least 2 positive cases and 1 negative case. The eval
    passes, and it fails when the step is removed (ablation).
  - **(c)** Out of static scope. The reason comes from a fixed list (needs a running system / deployed config / infra
    outside the repo / process-only), and the status names the runtime check the report tells the user to run.
- The denominators are fixed: all items. Each list's item count comes from a fetched source and is committed before
  any authoring.
- ASVS items may share an eval by verification family. The grouping is committed before authoring.
- A costed pilot on one list comes first. If the pilot projects G1 over its G8 line, the owner decides before the
  rest is authored.
- Pass, for each list: 0 unstatused items. (c) ≤ 40% for the five Top lists and ≤ 50% for ASVS L2.
- An independent lane audits every (c) label and a random 20% of the (a)/(b) labels. That lane did not write the
  matrix and runs on a different model. A rejected label counts as unstatused. A rejection rate above 10% fails
  the gate.

**G2 Public ground truth (OWASP BenchmarkJava v1.2; BenchmarkPython is held back for C).**
- Run `review_checks --full` plus the skill on BenchmarkJava v1.2.
- Score against its expected-results CSV, as TPR − FPR per category.
- The skill runs on at least 20 cases per category. The sample is drawn by a fixed seed before any run, and every
  scanner is scored on the same sample.
- Pass:
  - every category ≥ 0.3;
  - ≥ 75% of categories ≥ 0.5;
  - the combined arm beats the best single hub scanner.
- The cap is $30. If it is hit before the sample is complete, the gate is NOT MET.
- G2 cannot stand in for G3 or G6. The report states which classes the Benchmark covers.

**G3 Real-repo recall (private clones, counts only, never public).**
- Ground truth is one row per finding (repo, class, severity, file, and line where the note gives one). The rows
  are extracted from the private audit notes before any scoring. The 10-31 tally was per class only.
- Before any re-measure, split the clones by repo into tune and holdout with a fixed seed. The split is stratified so
  that every class with ≥ 5 findings keeps ≥ 5 in holdout wherever the repo counts allow. From then on, detector
  work uses tune only.
- The match rule is written before scoring:
  - Located rows match on same file, line ±5 (or same file when the note gives no line) and same class.
  - Unlocated rows are matched on the finding text by an independent adjudicator.
  - Recall is reported separately for located and unlocated rows. The pass uses all rows.
  - The same adjudicator settles disputed matches.
- Pass, on holdout:
  - overall recall ≥ 50%;
  - every class with ≥ 5 findings ≥ 30%;
  - precision ≥ 0.70 on 50 random reported rows;
  - classes with fewer than 5 holdout findings are reported as low-n, not passed. A ready claim names each one as
    not measured on real code.
- A scanners-only re-run is a leading-metric re-measure, not a G3 attempt. G3 needs `--full` plus the skill.
- Kill: if the S1 re-measure leaves any class with ≥ 5 findings at 0, that class is the next detector lane, ahead
  of any S2 work.

**G4 Diff bench vs rival.**
- A new blind set: n ≥ 30, at least 6 decoys, weighted to the gap classes.
- The rival prompt runs at its upstream head; its sha and date are recorded.
- Two Perun arms: prose-only (same tools as the rival) and installed-default (review_checks + skill, Bash allowed).
  The claim uses installed-default; both arms are reported.
- WIN = a one-sided sign test on paired wins vs losses with p < 0.10, at ≤ rival dollar cost. Wall time, including
  scanner time, is reported.
- Not significant = tie. A tie at higher cost is a loss.

**G5 Dependency currency (owner ask: all libraries).**
- Scope:
  - direct and transitive dependencies (from the lockfile) and manifest-vs-lock drift;
  - container base images;
  - CI action pins;
  - end-of-life runtimes and frameworks (EOL source named and fetched);
  - vendored code (flagged);
  - multi-manifest monorepos.
- Each row gives current, latest, how far behind, known-vulnerable (OSV, KEV-listed first) and an upgrade target.
- "Latest" is defined per ecosystem before fixtures exist:
  - stable releases only (no pre-release, yanked or deprecated versions);
  - the LTS channel is respected for runtimes (Node, Java);
  - Go major-version module paths are treated as separate modules.
- Scoring also checks that every upgrade target resolves and that KEV-listed rows come first.
- A counts-only currency run on the private clones is reported, not gated.
- Fixtures: 8 repos, one each for npm, pip, go, maven, gradle, cargo and composer, plus a Dockerfile/Actions
  monorepo.
- Ground truth is written by the blind lane at build time: the pinned versions, plus a registry snapshot of latest
  versions with its date. Ground truth is not the detector's own wrapped tool. The scored run happens within 24h of
  the snapshot, or the snapshot is re-taken.
- Each fixture also pins at least 3 dependencies at their latest version (decoys).
- Pass: 0 misses and 0 decoys reported as outdated. NOT RUN in a pass run counts as a miss.

**G6 Data/API calls.**
- The apps are blind-authored, across Express, Flask/FastAPI, Django, Spring, Go net/http and Next.js. Each
  framework has at least one global-middleware auth fixture and one decorator auth fixture.
- (i) Routes: 30 missing authn/authz or object-level check, plus 30 protected decoys. Pass at recall ≥ 0.85 and
  precision ≥ 0.80.
- (ii) Outbound calls (TLS verification off, SSRF, no timeout, secret in URL or log): 30 positives plus 15 decoys.
  Pass at recall ≥ 0.85 and precision ≥ 0.80.
- (iii) Six classes, each with 12 positives plus 8 decoys:
  - rate limits on auth and costly endpoints;
  - CSRF;
  - cookie/session flags;
  - PII in logs;
  - PII in data (committed data, fixtures, seeds, dumps, analytics payloads, unencrypted at-rest fields);
  - prompt injection.
  Each class passes at recall ≥ 0.75 and precision ≥ 0.75.

**G7 Validated fixes.**
- The denominator is every seeded positive in G6 and in G2's sample. Unfound means unfixed.
- For each positive, the blind lane pre-writes:
  - an exploit test;
  - at least 2 variant payloads;
  - a functional test of the legitimate path.
  All of them are hidden from the fixer. Validation runs on the exploit and on every variant.
- A fix counts only if all of these hold:
  - the patch applies;
  - the exploit test is now blocked;
  - the functional test passes before and after;
  - the project's tests pass;
  - a lint confirms none of these:
    - a suppression;
    - a detector or config change;
    - a deleted or skipped test;
    - a removed route or feature (the route inventory must be unchanged);
    - a literal copied from a test.
- Pass: ≥ 60% validated and 0 gamed. (v2 said 70%, but unfound positives now count as unfixed.)
- Private-clone fixes are reported as counts and not gated.

**G8 Cost and budget.**
- G4's cost rule applies. Report the cost per whole-project audit.
- Paid estimate, including C: about $140 (G4 2x$15, G2 $25 + C $20, G1 ablation evals $15 subject to the pilot,
  G3 2x$8, G6 2x$6, G9 scale $10, G7 $8, G10 $3).
- Spend runs only under the bench budget and the quota stop. If the budget runs out, the bar is NOT READY.

**G9 Completeness and scale (end-to-end).**
- A whole-project audit of each G6 app lists 100% of its routes, compared with the blind lane's inventory, and 100%
  of lockfile dependencies, with every matrix row filled.
- A ≥ 200k-LOC public repo finishes in ≤ 60 min. There is no silent truncation: anything skipped becomes a NOT
  CHECKED row.

**G10 IaC, CI and secrets.**
- Blind seeded set with 20 positives and 10 decoys. Positives include:
  - Actions injection or unpinned actions;
  - a Dockerfile running as root;
  - a public bucket in Terraform;
  - a privileged K8s pod;
  - a secret in the tree;
  - a secret in history only.
- Pass at recall ≥ 0.80 and precision ≥ 0.80.

**C Confirmation.**
- New blind sets for G4, G6 and G10, authored after S3.
- G2's rules run on BenchmarkPython v0.1, a second labelled corpus held back since today.
- G3's rules run on a project manually audited after today. This is required, and it is owner-gated. Without it
  there is no ready claim, only "ready pending real-code confirmation".

## Kill ledger (24 kills → change or rebuttal)

**G0**
- Form-only (Opus), and all not-checked passes (Haiku). Changed: a pass needs a check that ran; false-pass ceiling
  ≤ 5%; cap of 40% not-checked on (a)/(b) items.
- Cited lines may not exist (Sonnet). Changed: the linter resolves every path and line.

**G1**
- The (c) denominator (Haiku, Sonnet). Changed: fixed denominators, plus the (c) caps.
- (b) is cheap (Sonnet, Opus). Changed: blind eval with at least 2 positives and 1 negative, the ablation must fail,
  and the 20% audit of (a)/(b).
- The LLM and Agentic lists are missing (Opus). Changed: both added.

**G2**
- Not the same sample (Haiku). Changed: the same seeded sample for every arm.
- Thin categories and contamination (Sonnet, Opus). Changed: at least 20 per category, a per-category floor, and the
  coverage statement. Rebuttal: contamination can't be removed from a public corpus. That's why G2 can't stand in
  for G3 or G6, and C uses a second corpus.

**G3**
- Not blind (Haiku, Sonnet). Changed: the tune/holdout split from today, the match rule fixed before scoring, and the
  adjudicator.
- Rebuttal: the 11-01 detectors already saw every clone, so the holdout is still partly contaminated. That is why C
  requires a new manual audit.

**G4**
- A noise win (Sonnet). Changed: the sign test.
- Scanner cost (Sonnet). Changed: wall time is reported, and dollars stay as the cost rule.

**G5**
- Direct dependencies only (Haiku, Opus). Changed: the full scope above.
- Circular oracle (Sonnet). Changed: the blind ground truth and the dated registry snapshot.
- NOT RUN (Haiku). Changed: NOT RUN counts as a miss.

**G6**
- No blind authoring, and unknown counted as a verdict (Haiku, Opus). Changed: both fixed.
- Wide intervals and no decoys in (iii) (Sonnet, Opus). Changed: more cases, decoys and precision floors, Wilson
  intervals, and the auth-style fixtures.

**G7**
- Self-selected denominator (Haiku, Sonnet, Opus). Changed: the seeded-positive denominator.
- Feature removal and vacuous tests (all 3). Changed: the pre-written exploit and functional tests, and the
  no-removal lint.

**G8**
- Over budget (Haiku). Changed: C is costed, and an overrun means NOT READY plus an owner ask.

**Missing gates**
- No end-to-end check (Sonnet). Changed: G9.
- IaC, CI and history (Opus). Changed: G10.
- Scale (Opus). Changed: G9.
- Statuses not tied to NOT RUN (Opus). Changed: G0.

**v3 re-attack (Opus, REVISE)**
- Unlimited attempts on a fixed set. Changed: one scored attempt per set, and the holdout is burned after use.
- Small-n point estimates. Changed: the Wilson lower-bound floor.
- A guided pass with no proof the step ran. Changed: per-project evidence, and the linter checks it.
- G1 unaffordable. Changed: counts are fetched, ASVS family grouping is allowed, and a costed pilot comes first.
- G7 payload denylist. Changed: hidden tests, blind variants, and the copied-literal lint.
- C real-code leg optional. Changed: it's required, and the unlisted-finding rule is added.
- PII in data untested. Changed: a separate PII-in-data class in G6(iii).
- G5 "latest" undefined. Changed: a per-ecosystem rule, target validity, KEV order, and a private counts run.
