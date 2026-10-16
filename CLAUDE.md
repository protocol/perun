# CLAUDE.md — working in this repository (AI-facing)

## What this is
This repo is a **portable bar**: a universal, deep code-review skill (the
default product) plus optional overlays that inject a gated-delivery pattern,
a pre-owner idea attack, a persisted-message structure rule, and a privacy-safe
upstream-contribution flow into a target repo. The crown jewel is `.claude/skills/deep-code-review/SKILL.md`; its depth
lives in that skill's `references/`. Sibling skills live under
`.claude/skills/agentic-delivery/`, `.claude/skills/idea-critic/`,
`.claude/skills/communication-structure/`, `.claude/skills/contribution/`,
`.claude/skills/product-discovery/`, `.claude/skills/agentic-ceo/`, `.claude/skills/growth-analytics/`, `.claude/skills/positioning/`,
`.claude/skills/business-ops/`, and `.claude/skills/product-output-safety/`.
Everything else (`README.md`,
`install.sh`, `docs/standards-index.md`) supports distributing and trusting
those skills.
There is no application to build and no runtime — the "product" is prose a
human or an agent executes. Default `install.sh` install is review-only; the
plugin manifest (`.claude-plugin/plugin.json`) ships every skill.

## How to work here
- **Edit the skill, not a copy of it.** Each skill has exactly one home
  (`.claude/skills/<name>/`). `install.sh` copies *from* there; never
  create a second copy anywhere in this repo.
- **No duplication — this is the repo's thesis.** The skill condemns duplicated
  logic; the repo must not contain a second copy of any checklist, principle, or
  definition. `SKILL.md` holds the map; each `references/` file holds depth
  `SKILL.md` doesn't. If you're tempted to restate a section, link to it instead.
- **Every reference file must be routed.** Each skill's `SKILL.md` must name each
  of its `references/*.md` by path with an explicit "read this when…" trigger.
  Progressive disclosure only works if the parent routes to it; an unrouted
  reference is dead weight and fails review.
- **Overlays stay public-safe.** No operator preferences, private intake
  routes, exact model denylists, or third-party identifiers. Chat voice is
  not vendored — point at the public caveman repository if a project wants
  compressed assistant prose. Persisted artifacts stay normal English.
- **Verify before you cite.** Any standard, version, date, or list added to the
  skill or to `docs/standards-index.md` must come from a source you actually
  fetched this session. Record the URL + verification date in
  `docs/standards-index.md`. Anything you couldn't fetch goes in the by-name list
  **without** a URL. Never paste a remembered link.
- **Docs map.** `docs/INDEX.md` has one line per doc. Open a doc only when its row
  matches; `bash scripts/land-release.sh --regen` rebuilds it and CI checks it.

## Definition of done (for a change here)
- The skill still reads as one coherent method; scope modes, report template, and
  the definition-of-done checklist stay internally consistent.
- Every `references/*.md` is routed from `SKILL.md`; every routed path exists.
- `bash -n install.sh` passes and `install.sh` still lands the skill with a
  `name:` matching the directory.
- `docs/standards-index.md` contains only URLs verified this session, each dated.
- The privacy/no-fabrication grep (below) is clean.
- A commit that edits any skill's `SKILL.md` or `references/*.md` also touches a
  mechanism (an `evals/evals.json`, a skill script, or `scripts/test-ci-gates.sh`)
  or carries a non-empty `No-Mechanism-Reason:` trailer; CI's "Prose lessons carry
  a mechanism" step enforces it, merge commits included. A commit whose only
  trigger-path change is `SKILL.md` frontmatter `version:` lines (a release stamp
  bump) is exempt.

## Hard rules (never violate)
- **No fabrication.** No invented findings, data, sources, metrics, CWEs, dates,
  version numbers, or line numbers. If a source won't confirm it, omit it or mark
  it `unverified`. When two sources conflict, trust the authoritative one and
  make no claim you can't back.
- **Confidentiality / privacy (first- vs third-party).** No secrets anywhere, and
  no *third-party* real names, company/team/client names, emails, internal IDs, or
  private hostnames — in code, comments, docs, fixtures, commits, PR bodies, or git
  history. Use fictional placeholders (`Acme Capital`, `jane@example.com`, "the
  operator") for everyone else. The project's **own intended-public identity is not
  a leak**: the public repository URL and the `LICENSE`/package author may stand
  where the project itself publishes them (e.g. in `README.md` or `LICENSE`), and
  the committed `.banlist.txt` bans only secrets plus generic patterns while real
  identifiers live in gitignored `.banlist.local.txt`. Treat drift **beyond** that
  stated-public surface as the finding. This mirrors the skill's principle 11. This
  repository is built partly from lessons mined out of private projects; those
  lessons are **generalized to their underlying principle** and stripped of every
  third-party identifier.
- **Do no harm.** Any edit is net-positive across every axis (clarity, accuracy,
  coverage, consistency) and never regresses another. Respect the existing
  structure; propose a restructure as a decision, don't impose it.
- **Confirm before destructive/irreversible/shared-state actions** (force-push,
  history rewrite, deletes, external sends). Local reversible edits proceed.

## Pre-commit check (run before every commit)
```bash
# no accidental identifiers/secrets (tune the pattern to real risks; a hit is a
# lead to triage, not necessarily a secret — but never commit an uncleared hit)
grep -rInE '(^|[^A-Za-z0-9])(AKIA|ASIA)[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,}|[sr]k_live_[A-Za-z0-9]{24,}|AIza[0-9A-Za-z_-]{35}|-----BEGIN [A-Z ]*PRIVATE KEY( BLOCK)?-----' . \
  --exclude-dir=.git && echo "BLOCK: potential secret" || echo "clean"
# every reference file is routed from SKILL.md
for f in .claude/skills/deep-code-review/references/*.md; do
  grep -q "$(basename "$f")" .claude/skills/deep-code-review/SKILL.md \
    || echo "UNROUTED: $f"
done
```

## Adding or updating a reference file
1. Write depth that `SKILL.md` genuinely can't hold (procedures, payloads, greps,
   worked patterns) — not a restatement of the checklist.
2. Add a "Read this when…" line at the top.
3. Route it from the matching domain section in `SKILL.md`.
4. If it cites a standard, verify the source and log it in
   `docs/standards-index.md`.
