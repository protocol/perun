# Perun security "ready" bar v2 (draft after council, 2026-11-03; pre-registered before any measurement)

Ready = every gate G0-G8 passes, then a confirmation re-run of G2, G3 and G4 on fresh sets authored after the
first pass. Perun never says "secure": ready means Perun can audit a whole project against named standards, show
evidence for each verdict, list what it did not check, and produce validated fixes. Thresholds below are fixed now;
changing one after any result restarts that gate on a fresh set.

Staged order: S1 = G0, G3 (re-measure), G5. S2 = G1, G6. S3 = G2, G4, G7, G8. Then confirmation.

**G0 Report contract (honesty).** Every whole-project audit report has: a per-standard table (ASVS 5.0 L2 chapter,
Top 10:2025, API Top 10:2023, CWE Top 25 2025) with pass / fail / not-checked per item and evidence (file:line or tool
row); a NOT CHECKED list; a static-vs-runtime section naming what needs a running system (deployed config, WAF,
runtime authz, vault, infra outside the repo); a dependency section. A deterministic contract linter fails any report
that says secure/safe/no issues without the scope line, or has an item with no status. Pass: linter passes 100% of
reports produced in G2/G3/G4; its seeded negative tests (blanket "secure", missing NOT CHECKED, unstatused item) fail.

**G1 Standards matrix.** A committed matrix gives every item of ASVS 5.0 L2, Top 10:2025, API Top 10:2023 and CWE
Top 25 (2025) one status: (a) deterministic detector with a seeded positive and negative test; (b) guided review step
with a seeded eval case; (c) out of static scope, with a reason from a fixed list (needs running system / deployed
config / infra outside repo / process-only) and the runtime check the report tells the user to run. Pass: 0 items
without a status; for the three Top lists, >= 80% of non-(c) items at (a) or (b); for ASVS L2, >= 50% of all items at
(a) or (b) and (c) <= 40%. An independent reviewer audits every (c) label; any (c) the reviewer rejects counts as
unstatused.

**G2 Public ground truth (whole repo).** `review_checks --full` plus the skill audit on OWASP BenchmarkJava v1.2 and
BenchmarkPython, scored against their expected-results CSVs (TPR - FPR per category). Scanners run on all cases; the
skill audit runs on a stratified random sample of 120 cases drawn by a fixed seed before any run (cap $25). Pass:
TPR - FPR >= 0.5 in >= 75% of categories, and the combined result beats the best single hub scanner on the same
cases.

**G3 Real-repo recall (private clones, counts only, never public).** `--full` plus the skill audit on the local audit
clones, matched to the manual findings. Pass: overall recall >= 50%; every class with >= 5 manual findings >= 30%;
precision on a random sample of 50 reported rows >= 0.70. Leading metric for the whole bar. Kill: if the first S1
re-measure leaves any class with >= 5 findings at 0, that class becomes the next detector lane before any S2 work.

**G4 Diff bench vs rival.** New blind set, n >= 30, >= 6 decoys, weighted to the gap classes, authored by a lane that
never reads the skill or the rival prompt; rival prompt at upstream head (sha + date recorded). Two Perun arms:
prose-only (same tools as the rival) and installed-default (review_checks + skill, Bash allowed). The claim uses the
installed-default arm; both are reported. WIN = more paired wins than losses at <= rival cost, or a tie at lower cost;
a tie at higher cost is a loss.

**G5 Dependency currency.** A deterministic detector lists every direct dependency with current, latest and how far
behind (major/minor), end-of-life runtimes and frameworks, known-vulnerable versions (OSV; KEV-listed first) and an
upgrade target. Pass on 6 fixture repos (npm, pip, go modules, maven, cargo, composer) pinned to old versions: 0
misses vs the package manager's own outdated output and vs osv-scanner; every outdated row has a target version.
Offline or registry unreachable = a NOT RUN row, never "up to date".

**G6 Data/API calls.** Seeded sets (fictional apps across Express, Flask/FastAPI, Django, Spring, Go net/http,
Next.js): (i) routes: 40 routes (20 missing authn/authz or object-level check, 20 protected decoys), every route gets a
verdict, recall >= 0.85 and precision >= 0.80; (ii) outbound calls: 30 cases (TLS verification off, SSRF, missing
timeout, secret in URL/log, decoys), recall >= 0.85, precision >= 0.80; (iii) rate limits on auth/costly endpoints,
CSRF, cookie/session flags, PII in logs, prompt injection: >= 10 seeded cases each, recall >= 0.80.

**G7 Validated fixes.** For each confirmed finding in G2's sample, G4 and G6, Perun emits a patch. A fix counts only
if: it applies; the project's tests pass; the original detector AND an independent check (a different tool or an
exploit test) no longer flag it; and a lint confirms the diff adds no suppression, no detector/config change, no
deleted or skipped test. Pass: >= 70% validated, 0 suppression-gamed patches.

**G8 Cost.** G4's cost rule, plus cost per whole-project audit reported for every G2/G3 run. Total paid spend for
the whole bar <= the remaining bench budget (estimate: G4 ~$20, G2 $25 cap, G3 ~$20, G7 ~$10).
