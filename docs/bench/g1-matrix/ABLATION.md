# G1 pilot: ablation protocol for the status (b) items

Read this before running or scoring `docs/bench/g1-matrix/ablate.py`, or before giving API1, API3, API5 or API10 a G1 status.

BLUF: an item gets status (b) only if its blind eval passes with the guided step and fails without it, under the rules below. They were fixed before any call was made. If the eval also passes without the step, the item is not (b).

## What is tested
- Guided steps: the existing paragraphs "API1 + API5", "API3" and "API10" in `.claude/skills/deep-code-review/references/security-api.md`. They were written before the evals, and their authors never saw them. They are frozen at the blob hashes in the table below and are not edited during or after the run.
- Evals: `docs/bench/g1-matrix/evals-b/` (12 fixtures, hashes below). See its README for how they were made. The coordinator read the fixtures before this protocol was written.

## Arms
- Model: `sonnet` in both arms, chosen before any call because it is the project's default model for lanes. The rival_eval default (`haiku`) was not used: a weaker model fails more often without the step, which would favor (b).
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
These fixtures are used once. If a fixture or step is edited, or the run is repeated after the first scored call, the result is a new eval. An infrastructure fault (no output at all, an API error, or a harness crash before any answer is saved) voids the attempt. It may be re-run once from scratch. A fault after the first answer is saved (an API error, a timeout, a missing quota reading or a harness crash) stops the run instead: items already decided keep their verdict, the rest stay unstatused, and there is no re-run. `ablate.py` exits 2 in both cases; this rule decides which one applies.

## If an item is not (b)
The item stays unstatused. There are two remaining paths: an (a) deterministic detector with seeded tests, or a new blind eval set authored under rules written down and committed before authoring. The steps are never edited to fit these fixtures.

## Frozen inputs
| Input | Value |
|---|---|
| model | `sonnet` |
| `SKILL.md` git blob | 05da29c4e0811866bb9361f8b0680e59e0aea20b |
| `security-api.md` git blob | 39bce3f1ba1a8aef53dfbb4b439679efdbe34029 |
| `evals.json` sha256 | 0522f25cb86a8ebe1110720c66ffc3df5da29a795bec90901187aaf8cbd7657f |
| `ablate.py` sha256 | 042a77a9ccf468add46b2a3b9aee33638ccfe87b8acc5761a28b959dc02a2c65 |
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

## Result (run 1, 2026-11-05)

BLUF: no item reached status (b). The run finished with exit 0, cost $0.23 on `sonnet` (15 calls), at plan-quota utilization 0.43. Raw answers and `result.json` are in `run1/`.

| Item | Stripped arm (pass per fixture) | Step arm | Verdict |
|---|---|---|---|
| API1 | 3/3 | not run (stop rule) | not (b): stripped arm passes every fixture |
| API3 | 3/3 | not run (stop rule) | not (b): stripped arm passes every fixture |
| API5 | 3/3 | not run (stop rule) | not (b): stripped arm passes every fixture |
| API10 | 2/3 (negative `api10-c` flagged) | 2/3 (negative `api10-c` flagged) | not (b): step arm fails a fixture |

On `api10-c`, both arms flagged the upstream JSON body and item array, which have no size bound. That is a plausible real weakness, so this negative was not clean on API10. The result stands as scored, and the fixtures are burned.

What this shows: on small single-file textbook cases, a model without these steps already finds the flaw, so the steps were not shown to matter. It says nothing about larger or multi-file code.

## Next path (decided 2026-11-05)

A decision council scored the options mixed 3.55, detect 2.95 and harder 2.50. Only two of five seats returned a valid answer, and both voted REVISE. Three adversarial checks (failure, irreversibility, hidden cost) each returned OK-WITH-MITIGATION.

- API3: an (a) detector for inbound mass assignment, where a request body is spread or bound straight into a model create or update. It starts with JavaScript and Python. Other languages and the over-exposure direction are listed as not covered.
- API5: an (a) status, extending `route_auth_map.py` to flag privileged routes (admin paths, role or permission changes, destructive actions on other users' records) that are guarded only by authentication.
- API1 and API10: a new blind eval set, then one preregistered ablation with no re-run. A fresh agent writes the set under rules committed before authoring: multi-file cases, authorization split across middleware, and negatives that are clean on every API class. If either item still fails, the fallback is a narrow-scope (a) detector, not (c). API6 and API9 already take (c) to 20% of the list, and moving API1 and API10 to (c) as well would leave no slack under the 40% cap.
- Before any label counts, an independent model audits each new detector on at least 30 held-out cases, written blind from a published seed.
- Kill criteria, by 2026-11-19:
  - Drop a detector whose precision is below 0.7 on its held-out cases.
  - Stop and re-plan on any audit rejection among these four labels. One rejection is already 25% of the four, over the gate's 10% line.

## Frozen inputs (b2)
| Input | Value |
|---|---|
| model | `sonnet` |
| `SKILL.md` git blob | 05da29c4e0811866bb9361f8b0680e59e0aea20b |
| `security-api.md` git blob | 39bce3f1ba1a8aef53dfbb4b439679efdbe34029 |
| `evals.json` sha256 | 99253eea05a670db58dbb98f0f125aa574bb80e9b8d100108e1396def0ed0526 |
| `ablate.py` sha256 | 0237163474d612a57a2e3207b500ff489623dac3949c307bb08e29cd49baa281 |
| fixture `fixtures/api1-a/auth.js` sha256 | 80b02388f7ab44b73a90a8f139ff5fd6e3eddf3f024f32efeecb8dc717638448 |
| fixture `fixtures/api1-a/db.js` sha256 | d0fc672e225e2dd7b57c0b07b2344a2c588f22e1b086ccc6d6490028c2e49328 |
| fixture `fixtures/api1-a/invoices.js` sha256 | f600236d1f7dfc51b73cd7fee1c53ae4fa164e1f5c442a20b548cb18227e6cdb |
| fixture `fixtures/api1-a/server.js` sha256 | be80e49b24692143dc09562852aa9285d5866b937659d02f1c690fca98c5371e |
| fixture `fixtures/api1-b/app.py` sha256 | 214adb9dc3bc9ce61a27e8437944cafd36dab4222a2eadc473489334e17fe442 |
| fixture `fixtures/api1-b/authz.py` sha256 | b2ecd234c26ed5cc9808e2054326f89ada7342ddec0d51e24d643a3a4917084d |
| fixture `fixtures/api1-b/models.py` sha256 | 928aec4f9ab6af02fd32aadce7de7e8f977a4b23c34fe72f4f2cba3fa06f41be |
| fixture `fixtures/api1-b/views.py` sha256 | b7574ddd7b2c82f05aa914ab49cef91e539f960d3bee0eb7a90cf4c1f38097c2 |
| fixture `fixtures/api1-c/authz.go` sha256 | 7c92155229fb1a48c3914285b5649811c4b7c96cab97d73ec47b7388c9499bea |
| fixture `fixtures/api1-c/handlers.go` sha256 | 1c0aca5f022e08bade980c6756d782d355477909439979bf0f3c1aa25e85291a |
| fixture `fixtures/api1-c/main.go` sha256 | 6e54c3a9b33ad1dc0067bf47ca56055c274dbfe2eb263d85d0dd0bd66328567b |
| fixture `fixtures/api1-c/store.go` sha256 | a8ff81b052629aaf5b39b9fc8e4a95373c430290709eb5512b245d61779ede56 |
| fixture `fixtures/api1-d/app.py` sha256 | 4f2a6b9ad2b0a180b2b7077f24f0e4c56c14b2c9dbb98d13be408965671699fb |
| fixture `fixtures/api1-d/guard.py` sha256 | 3c75a0e4d37251d89852065d3459c9281b948e85be52e489a58fec68ab5b22a8 |
| fixture `fixtures/api1-d/routes.py` sha256 | 21ba2816fcffc7caacf6881911a0efdfb3c517883826a48668cc6300a1d75012 |
| fixture `fixtures/api1-d/store.py` sha256 | 30aac024b76194651fe8d836f10f6d16a2858ab6abc46aa4eda8090113e2aa26 |
| fixture `fixtures/api1-e/index.js` sha256 | 4fe48a63df5cb54ddbddc388a8e4092644946c484e584bd7a2146a14dcbaaba9 |
| fixture `fixtures/api1-e/policy.js` sha256 | 5f60877ac2b62cecbd4ff0d3235b2bd4b459bc8242364e36f7d57e290df4dd03 |
| fixture `fixtures/api1-e/projects.js` sha256 | 16d90585f6d160a7ef13af8b669f46b396321cb4964f18721cadc280c3137e1b |
| fixture `fixtures/api1-e/repo.js` sha256 | 041711ee0d9b8e69e72135424e20fe70ac3abbc65793d0a5d23b45049c715596 |
| fixture `fixtures/api10-a/app.py` sha256 | c7b767dab46ac2b16cb51be479140685367ae74f3750bc4189d9e4413473319f |
| fixture `fixtures/api10-a/partner_client.py` sha256 | 60bf5431ef3a4b87de6a5bd0c363075dc7ef9dd88caf1a7918bae5f65289a034 |
| fixture `fixtures/api10-a/rate_store.py` sha256 | 0bd50fa210aa0927e692d9c5f7341a6bfd343ef3b1faacf47bcb31bc9c68ef14 |
| fixture `fixtures/api10-a/report.py` sha256 | 4c11efb592c17ada96ff706174fe011b4e7f3a930f94ad6e7f128d62334ef6cf |
| fixture `fixtures/api10-b/carrier.js` sha256 | 0e646dd024c793a03687b141c1f140038b1b8c8a380284ad2e25fbeca251ee8a |
| fixture `fixtures/api10-b/labels.js` sha256 | 95efa6fe92ba4342a9c703a62b7d0d80afead2d262da3f51c50e0baf228c8c48 |
| fixture `fixtures/api10-b/routes.js` sha256 | a7b492ea984a922b94889e1c942d7fd63dcb15e0d72b0706769bcbe22aa2780d |
| fixture `fixtures/api10-b/server.js` sha256 | d0a1c93de8108e5134714404c6ffae939b7d41cd42af15c7c722e99e1d307753 |
| fixture `fixtures/api10-c/client.go` sha256 | de153e77b00d4ec127638796e3e8a255a3052355c5799f77f6997827e73671ef |
| fixture `fixtures/api10-c/main.go` sha256 | 329754f4480aba7c54c3d2492a8fc130f2293b24c1ed77b5baaafa65bdafbb67 |
| fixture `fixtures/api10-c/parse.go` sha256 | bf0c0e5b1ff2663bbe809e047ad58ef12f86f28edb45258e62fe101e7baf5c5f |
| fixture `fixtures/api10-d/app.py` sha256 | 8b4cd6e8738dac1d97dd05ffec3bf8f58338ee5dd670ea63f96cdcec4895dd25 |
| fixture `fixtures/api10-d/catalog.py` sha256 | aecdf7983e0fc3860ccbf7bb14ebf41c6765faf28d578bf5a9d58a6d3259c24e |
| fixture `fixtures/api10-d/checks.py` sha256 | e3c3f0c51b52b41b6abb7c25b178ead3c10bca8a7d1bbc242115d14cc580324c |
| fixture `fixtures/api10-d/vendor.py` sha256 | 08e2052ca80a33b09d6f76251a1bc1abe3c84faaf02ec133cd9e3a6d26c0599c |
| fixture `fixtures/api10-e/cache.js` sha256 | 596ff9ab8c0f37d865e46d5169414b3f93ef7ef350bd07eac3d3e63a9cae8ed5 |
| fixture `fixtures/api10-e/directory.js` sha256 | 21e6452b6bc0de31cbbb2278b1693972a722ef7f7963015efc541d92529a159d |
| fixture `fixtures/api10-e/sanitize.js` sha256 | 29e6ebf0c40f60c5169ce0203ff6f9090c546f9d77e778d05f1bd4da85ff071e |
| fixture `fixtures/api10-e/server.js` sha256 | e85d7e3adf54a87de5538f8cc1581692c456d261f465bcc1d7ef5b6740486ee4 |
