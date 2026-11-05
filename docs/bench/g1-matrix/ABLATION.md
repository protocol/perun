# G1 pilot: ablation protocol for the status (b) items

Read this before running or scoring `docs/bench/g1-matrix/ablate.py`, or before giving API1, API3, API5 or API10 a G1 status.

BLUF: an item gets status (b) only if its blind eval passes with the guided step and fails without it, under the rules below. They were fixed before any call was made. If the eval also passes without the step, the item is not (b).

## What is tested
- Guided steps: the existing paragraphs "API1 + API5", "API3" and "API10" in `.claude/skills/deep-code-review/references/security-api.md`. They were written before the evals, and their authors never saw them. They are frozen at the blob hashes in the table below and are not edited during or after the run.
- Evals: `docs/bench/g1-matrix/evals-b/` (12 fixtures, hashes below). See its README for how they were made. The coordinator read the fixtures before this protocol was written.

## Arms
- Both arms make one no-tools model call per fixture. The system prompt is `SKILL.md` followed by `references/security-api.md`. The user prompt is the fixture files, each under its path, then the API1 to API10 labels with titles only, then the output instruction. The labels and the instruction are identical in both arms.
- Step arm: the reference as committed.
- Stripped arm: the same text with the three item paragraphs removed. No other byte differs. A test asserts that the stripped text has no match for IDOR, BOLA, BFLA, mass assignment, over-posting, allow-list of bindable fields, privileged verb, or upstream response.
- Fidelity: this is not the installed agentic skill. `security-appsec.md` is not loaded in either arm, so the API1 + API5 paragraph's pointer to the A01 matrix has no target in the step arm. A result is a claim about these steps on these textbook fixtures only.

## Scoring (deterministic, `ablate.py score`)
- The model ends its answer with one fenced JSON list of findings `{file, line, owasp_api_2023}`.
- Positive: a hit when some finding has the truth file and the item's label. Line numbers are not compared, because each positive holds only one flaw.
- Negative: passes when no finding has the item's label.
- Unparseable output counts as no findings. It is never re-asked.

## Order, stop rule and confirmation
1. Stripped arm on all 12 fixtures.
2. If the stripped arm passes every fixture of an item, that item is not (b), and no step-arm calls are made for it.
3. For every other item, the step arm runs on all 3 of its fixtures.
4. A fixture is a candidate when the step arm passes it and the stripped arm fails it. Each candidate gets 2 more calls in each arm. It is discriminating only if the majority of 3 agrees in both arms.
5. On every fixture of a confirmed item, the step arm must pass by majority. A fixture with one step-arm call counts as a majority of 1.
6. An item is (b) when its eval passes in the step arm and it has at least one discriminating fixture.

## Budget
- The cap is $15 for the whole G1 ablation, checked against spend plus calls in flight before each call. Plan-quota utilization must be below 0.8, read before the first call and after each one.
- If the cap stops the run, any item not yet decided stays unstatused.
- Every raw answer is saved under the run's output directory, together with spend and utilization.

## One attempt
These fixtures are used once. If a fixture or step is edited, or the run is repeated after the first scored call, the result is a new eval. An infrastructure fault (no output at all, an API error, or a harness crash before any answer is saved) voids the attempt. It may be re-run once from scratch.

## If an item is not (b)
The item stays unstatused. There are two remaining paths: an (a) deterministic detector with seeded tests, or a new blind eval set authored under rules written down and committed before authoring. The steps are never edited to fit these fixtures.

## Frozen inputs
| Input | Value |
|---|---|
| model | `haiku` |
| `SKILL.md` git blob | 05da29c4e0811866bb9361f8b0680e59e0aea20b |
| `security-api.md` git blob | 39bce3f1ba1a8aef53dfbb4b439679efdbe34029 |
| `evals.json` sha256 | 0522f25cb86a8ebe1110720c66ffc3df5da29a795bec90901187aaf8cbd7657f |
| `ablate.py` sha256 | 7319c42976845e04a82fe367df0bc23d7b20a88abe0add8213a0bed62975d996 |
| fixture `fixtures/api1-a/orders.js` sha256 | 57c9e32790de78eba9e581f83b06defe1d62a64ba9a7b1951962217d88e016c7 |
| fixture `fixtures/api1-b/notes.py` sha256 | 9f8402cbfd31252fd03d587ad642e132606c9ee94fb94b74c109e3a1de8b2d5e |
| fixture `fixtures/api1-c/views.py` sha256 | 6de79ded9b6d97f5f0f7e3afc2eaa7bc4d5da7941ecd882e6140195b2d20de48 |
| fixture `fixtures/api10-a/sync.py` sha256 | 0a7ef71d107be1833295e9be87a30823f24d4f6b9a04355ab36a030ada776de3 |
| fixture `fixtures/api10-b/fetch.go` sha256 | 2fd4cb9b196c74ae7bd3de4865e21736a0105e7ff3c3a75fbea3e6f09d00800a |
| fixture `fixtures/api10-c/sync.js` sha256 | 114bf22e3fb02b8bba1d33a0be1cae08057fd9d626ac404c982ae953a7bd8954 |
| fixture `fixtures/api3-a/views.py` sha256 | 9fd77ae579e22861c4047719438ea37f56e04f5eb274cc9238f5d78e19154f68 |
| fixture `fixtures/api3-b/AccountController.java` sha256 | 03f7766811f1532082d57bfc6d43597293da7009455a546a8c9a0de37cfa1342 |
| fixture `fixtures/api3-c/profile.js` sha256 | 05da108dd16bb5383ed854a42d067842b3a84cb0fb92ac1c35407803e31785da |
| fixture `fixtures/api5-a/main.go` sha256 | c2c5293b48613ce63804bff6d0b6a97b7fe2ddedc39cd1ae2ea2768fb4ca5abe |
| fixture `fixtures/api5-b/users.js` sha256 | b0a67bdf8980f4f851f5812148ad11fb6dee06918e7b21a9d579e98e3677052b |
| fixture `fixtures/api5-c/users.py` sha256 | 359841f14d23052ba4bdab403dfefdc1cb4d6508d570a07f12c8023d0503f02a |
