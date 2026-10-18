# Testing ML pipelines, served models, and notebooks

Read this when the target trains or serves a classical ML model, makes consequential model decisions about people, or commits notebooks. Split from `testing-and-evals.md`; the general test taxonomy and smells there apply to every review.

## ML pipeline correctness — data leakage & training reproducibility

Distinct from AI evals (`testing-ai-evals.md`, which score a model's *output*): these are the
*pipeline* defects that make a reported metric **false** — the classical-ML sibling
of the LLM golden-set contamination rule. (Temporal / as-of *feature* leakage in a
train/serve pipeline is in `data-ml.md`; this is the train/test
split-hygiene and reproducibility half.)
- **Split first; never fit on test.** Data leakage is "information that would not be
  available at prediction time is used when building the model," giving "overly
  optimistic performance estimates" (scikit-learn). Check: the data is **split into
  train/test before any preprocessing**; a scaler / encoder / imputer is **fit on the
  training subset only** (fitting on all data leaks the test distribution — a
  Pipeline keeps cross-validation and tuning from leaking); **no target leakage** (a
  feature derived from the label or from the future); and **no duplicate rows across
  splits**. A leaked split doesn't fail — it *passes too well*, so the tell is an
  implausibly high score, not an error.
- **The split must respect group and time structure, and resampling happens inside the split.** Beyond fit-on-train, the *split strategy itself* leaks when rows aren't i.i.d.: a plain `KFold` scatters **correlated rows that share a group** (many samples per patient / user / device) across train and test, so the model memorizes the group and the score doesn't predict a genuinely new group — "the i.i.d. assumption is broken if the underlying generative process yields groups of dependent samples"; use `GroupKFold`, which "ensures that the same group is not represented in both testing and training sets" (scikit-learn). For **time-ordered** data a shuffled `KFold`/`ShuffleSplit` trains on the future to predict the past — the same source warns these "would result in unreasonable correlation between training and testing instances ... on time series data"; use a forward-chaining `TimeSeriesSplit`. And **class-imbalance resampling (SMOTE / over- / under-sampling) belongs inside the fold, on train only**: resampling the whole dataset before the split both leaks and makes the *test set artificially balanced* — the model then "will not be tested on a dataset with class distribution similar to the real use-case" (imbalanced-learn) — so the metric describes a distribution production never sees. All three **pass too well** rather than erroring, the same tell as the leaked-split rule above. (Distinct from the as-of *feature* leakage in `data-ml.md` — this is split *structure*.)
- **Training is reproducible, so a metric delta is attributable.** Retraining on the
  same data should yield the same model; unseeded RNG and unpinned data / model / code
  versions make a score change unattributable — you can't tell a real regression from
  noise. Seed the training RNG and pin the data + model + code version behind each
  reported number (Breck et al., *The ML Test Score*, 2017).

## ML in production — drift monitoring & safe model rollout

The lifecycle sibling of the two sections above: §"ML pipeline correctness" verifies the model
was **trained** honestly and `data-ml.md` verifies a feature is **computed the same**
for training and serving — this is the **post-deployment** half, where a model that was correct
at ship time silently decays, or a swap ships a quietly worse one. Both are invisible to the
checks that guard training.
- **Monitor drift, not just uptime.** A served model **silently loses accuracy** (no error is
  thrown) as the live input distribution drifts from the training distribution **over time** —
  distinct from `data-ml.md`'s train/serve *parity* check (two computation paths at one
  instant); this compares live inputs to the training baseline as time passes. Monitor the **input-feature
  distribution** and the **prediction distribution** (a sudden shift in either is the early
  signal), plus realized **performance against ground truth** — but **ground truth often lags** (the
  label for today's prediction lands days or weeks later), so quality is delayed and the thing
  you alert on in the meantime is a **proxy** (distribution shift, a confidence drop). A model
  with green infra dashboards and no distribution/quality monitoring is unmonitored where it
  matters (cf. the monitoring category of the ML Test Score cited above; the generic signal
  plumbing is `observability.md`).
- **Roll a new model out behind a quality gate, not a health check.** A new model version is a
  behavior change, not just a deploy — and **green error-rate and latency do not mean the new
  model is as good** (they miss a quieter, worse model). Prove the candidate on **prediction
  quality** first: **shadow** it (run it on live traffic in parallel, compare outputs, serve
  none), or **canary / champion-challenger** to a slice with a **prediction-quality** promotion
  gate (not just error/latency), keeping a **rollback path** to the incumbent. Because ground
  truth lags, a model canary needs a **longer, quality-based bake** than a code canary —
  promoting on a few minutes of green health is how a worse model reaches everyone. This
  specializes the generic canary/rollback discipline in `release-engineering.md` to the ML case,
  where the load-bearing signal is delayed prediction quality, not error rate.

## ML fairness — detect it in review, never certify it

**Scope gate — apply this first.** This lens applies only when the model makes a
**consequential decision about people** (credit, hiring, housing, moderation, benefits,
ranking that gates access) **and** the data carries at least one group dimension or a proxy
for one. If you cannot name the decision, the affected people, and a group dimension present
in the data, the lens **does not apply — say so and stop**. Hunting fairness in a model with
no protected-group dimension manufactures a finding — the "stricter than the standard" defect
(`method-situational.md`).

Where it applies, bias is **systemic, statistical, and human** (NIST SP 1270); computational
metrics are necessary, not sufficient. The review question mirrors this suite's own thesis —
*not just whether the model is biased, but whether it does what is claimed* (NIST SP 1270).
Detect, do not grade:

- **Protected attributes and proxies.** Is a protected characteristic (race, sex, age, …) used
  as a feature — **disparate treatment** — or **not used but proxied** by a correlated feature
  (zip, name, device, purchase history) — **disparate impact**? A proxy claim is **demonstrated**
  — show the feature's correlation with the group attribute *in this data* — never asserted from
  a stereotype; and **absence of the protected attribute does not establish fairness**, since a
  model can discriminate through proxies alone. Dropping a suspected proxy without measuring
  outcomes is not a fix — it removes signal untested and other proxies may remain.
- **Fairness is measured, and the metric is chosen on purpose.** A consequential model gated
  only on **aggregate** accuracy carries no fairness signal — it can be accurate overall and
  systematically worse for a subgroup. Require a **disaggregated** evaluation by group, and
  require the team to **state which fairness metric they target and justify it against the
  decision** (demographic parity and error-rate balance answer different questions — the metric
  must fit the decision, not be picked for looking best). The **absence of any stated, justified
  choice** is the finding — not your preferred metric. Show coverage; never a fabricated
  "0% bias" (the coverage-not-grade rule; `product-output-safety` MEASURE).
- **Documentation.** On a consequential model, flag a **missing model card** — intended use,
  out-of-scope uses, and **per-subgroup** measured performance (Mitchell et al., 2019).
  `product-output-safety` (when installed) prescribes *producing* the card; in review, flag that
  it is **absent**.
- **Dataset bias is a data-quality dimension.** Group representativeness in the training set is
  the statistical-bias leg — measure it as a completeness/representativeness dimension under
  `data-quality.md` §4, do not re-derive it here.

**🚩** a consequential-decision model whose only gate is aggregate accuracy; a protected
attribute or a demonstrated proxy in the feature set with no disaggregated evaluation; a
"fair" / "unbiased" claim carrying no named metric, no per-group numbers, and no model card.

This is the **detection** lens for a default review; the output-harm guardrail — inventory the
bias harm, never certify "unbiased", report residual risk — is the `product-output-safety`
overlay, not restated here. Whether a demonstrated disparity is **unlawful
discrimination** is a legal determination — route it to counsel (`business-ops` names the
regime); the code finding is the **missing measurement or unstated metric**, never a legal verdict.

## Notebook review — hidden state & committed outputs (data-science code)

A Jupyter/Colab notebook is code with two failure modes a normal source review misses, both distinct from the
ML-pipeline correctness above:
- **Out-of-order execution → hidden state.** A notebook's results reflect the order cells were *run*, not
  top-to-bottom source order; an output can depend on a variable set by a cell since edited, moved, or deleted,
  so the committed `.ipynb` may not reproduce from a clean kernel. The only honest check is **Restart & Run
  All** (or `jupyter nbconvert --execute` / `nbclient` in CI) from a fresh kernel — a notebook that only works
  in its author's live session is not reproducible, and "it ran for me" is not evidence. 🚩 a committed
  notebook with non-monotonic `execution_count`s, or a CI that never executes it fresh.
- **Committed output cells leak data and secrets.** `.ipynb` stores cell *outputs* in the file: a printed
  `df.head()` with real rows (PII), an API token echoed in a repr, credentials in a traceback, a base64 image,
  or megabytes of data — committed into git history where a diff-scoped review never looks. Strip outputs before
  commit (`nbstripout`, a `--clear-output` pre-commit hook, or a CI gate); a secret that reached a commit is compromised and must be **rotated**, not just stripped (cross-ref `security-appsec.md` Secrets), and treat a committed output cell like any other emitted value (cross-ref `observability.md` Logs & traces and `privacy-compliance.md`). 🚩 an
  `.ipynb` with populated `outputs` / `execution_count` in the diff and no output-stripping gate.
