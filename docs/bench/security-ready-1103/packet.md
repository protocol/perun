# Decision packet: what does "ready" mean for Perun as a security audit product?

## The owner's ask (verbatim, 2026-11-03)
"define 'ready' by brainstorming it with decision council and then triple checking with evil twin - Perun must be able
to audit, review, and investigate our codebases/projects to ensure they're the most secure and safe and best secured,
all libraries and dependencies up to date, any data/API calls fully secured, etc. - every project/codebase must align
with best security practices and standards and Perun must be able to fully review it and confirm or suggest
improvements and fixes"

## What Perun is
A public, MIT-licensed skill suite for coding agents. Its review skill (deep-code-review) is prose a model follows
(SKILL.md plus references/*.md) and a scanner hub, `scripts/review_checks.sh`, that runs installed OSS tools and
in-house detectors over a diff (`--history`, diff mode) or a whole tree (`--full`). `scripts/security_verify.py`
re-checks findings. Missing tools are reported in a NOT RUN list, never silently skipped.

Wired today (from review_checks.sh on main):
- OSS: gitleaks (tree + last 1000 commits of history), trufflehog, semgrep, trivy (secrets), osv-scanner,
  guarddog, shellcheck, ruff/pyflakes, go vet, tsc, node --check, jq; tool-hub routes for zizmor, bandit, gosec,
  grype, checkov, hadolint.
- In-house detectors: route-auth, tenant-scope, attempt-limit, header-config, committed-data, invisible-chars,
  sibling-sweep.
- Dependency *currency* (outdated but not vulnerable, end-of-life runtimes) exists only as prose guidance
  (references/dependency-currency-and-upgrades.md); there is no deterministic currency detector.

## Evidence so far (aggregates only)
- Diff bench (2026-10-26, blind held-out set, n=8): Perun tied the rival (an open-source LLM security-review
  GitHub Action's prompt) at 8/8 recall and 0.80 precision, but cost 1.39x. Owner rule: a tie at higher cost is a
  LOSS. The bench's Perun arm could only Read/Grep/Glob, so it measured the prose, not the scanners.
- Real-repo recall (2026-10-31, private projects, counts only): scanners matched about 13% of 360 manual audit
  findings. Classes with 0 scanner hits: rate-limit/DoS, XSS, injection, authz/IDOR, prompt injection,
  cookie/session, CSRF. PII in data/logs had the highest manual severity score. Since then (11-01/11-02) semgrep
  rules for XSS and injection, the header-config and attempt-limit detectors, and the history secret pass landed;
  real-repo recall has not been re-measured after them.
- n=8 is too small to separate tools; Wilson intervals at that n span roughly 0.6-1.0.

## Standards already verified in the repo's standards index
OWASP ASVS 5.0.0 (May 2025), OWASP Top 10:2025 (A03 now covers vulnerable and outdated components), OWASP API
Security Top 10:2023, CWE Top 25 (2025), OWASP Top 10 for LLM Applications 2025, OWASP Top 10 for Agentic
Applications 2026, OpenSSF Scorecard checks, OSV, CISA KEV.

## Fixed constraints (not votable)
1. Perun never certifies a project "secure". "Confirm" means: confirmed against a named yardstick (a standard
   item or a check), with evidence, plus an explicit NOT CHECKED list and a static-vs-runtime split (what static
   review cannot verify: deployed config, WAF, runtime authz, secrets in the vault, infra outside the repo).
2. A tie at higher cost is a loss. No fabrication: every claim cites a file:line, a tool row or a fetched source.
3. Paid bench budget: $100 from 2026-10-26, abort at plan-quota utilization >= 0.8. Free cross-vendor models
   preferred for judging.
4. Public-safe: private project data stays local and is reported as counts only.
5. Every bar is pre-registered before measurement; blind fixtures are authored by a lane that never reads the
   skill or the rival prompt.

## Candidate definitions of ready (score each; propose missing components in your claims)

**bench-only** (the current bar): A) blind seeded diff bench WIN vs the rival at upstream head, n>=30 with >=6
decoys, gap-class weighted; B) every proven OSS tool in a fetched survey wired with tests or rejected with a
reason; C) on the private clones, no gap class with >=5 manual findings left at 0 detections.

**standards-matrix**: every item of ASVS 5.0 L2, Top 10:2025, API Top 10:2023 and CWE Top 25 (2025) gets one
status in a committed matrix: (a) deterministic detector with a seeded positive and negative test, (b) guided
review step in the skill with a seeded eval, or (c) out of static scope, with the reason and the runtime check
the report tells the user to run. Ready = 0 items without a status and >= X% at (a) or (b).

**outcome-recall**: measured detection on real code. Whole-repo `--full` + skill audit over (1) public
deliberately vulnerable apps that publish their vulnerability list (ground truth) and (2) the private clones.
Ready = recall floor per class (e.g. >= 50% per class with >= 5 known findings), precision floor on clean
negative-control repos, and no class at 0.

**layered**: all three, plus the owner's explicit asks as named gates:
- Dependency currency: report every outdated direct dependency (major/minor behind latest), EOL runtimes and
  frameworks, and known-vulnerable versions (OSV, KEV-flagged first), with an upgrade path; measured against the
  package manager's own outdated output on fixture repos (0 misses).
- Data/API calls: every route has an authn/authz verdict; outbound calls checked for TLS verification, SSRF,
  timeouts, secret handling; rate limits on auth and costly endpoints; PII in logs.
- Fixes: each confirmed finding gets a patch; ready = patch applies, tests pass, re-scan clears it, on a seeded set
  (fix-validated rate >= Y%).
- Report contract: per-standard pass/fail/not-checked table, NOT CHECKED list, static-vs-runtime split, severity
  with exploit path, never a blanket "secure".
- Cost: paid-arm cost <= rival at equal or better recall.

## Criteria (fixed before scoring)
owner-fit (covers the owner's ask), falsifiable (measurable pass/fail, gameable only with effort), honesty (cannot
produce a false "secure"), cost (bench and maintenance), time-to-ready.
