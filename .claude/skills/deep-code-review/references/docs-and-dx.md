# Documentation, DX & standards-imprint

Read this when reviewing (or writing) a project's documentation, its setup /
developer experience, its **repository hygiene** (license, security policy,
contribution + ownership files, branch protection, changelog), its **cross-agent
instruction files** (`CLAUDE.md` / `AGENTS.md` and peers), or when the review
should **leave durable standards behind** so future contributors and agents hold
the quality bar on later iterations. Expands section O of `SKILL.md`.

---

## Documentation architecture

Good docs aren't one long file — they answer distinct needs in distinct places.

- **Diátaxis** — four types, kept separate: **Tutorials** (learning-oriented,
  get a newcomer to a first success), **How-to guides** (task-oriented, achieve
  a specific goal), **Reference** (information-oriented, describe the API/config
  precisely), **Explanation** (understanding-oriented, the why and the
  trade-offs). A page that tries to be all four serves none. Misfiled content is
  a finding.
- **C4 model** for the architecture diagram — four zoom levels: **Context**
  (the system and its users/externals), **Container** (the deployable
  apps/services/stores), **Component** (the major parts inside a container),
  **Code** (only where it earns its place). Most READMEs need Context +
  Container. Use Mermaid so the diagram lives in version control and can't rot
  into a stale PNG.
- **ADRs (Architecture Decision Records)** — one short record per significant,
  hard-to-reverse decision: context, the decision, the alternatives, the
  consequences. They give future readers (human and AI) the *rationale trail* a
  diff can't.

## README (human-facing) — leadership-grade

- **BLUF**: the first lines say what it is, what problem it solves, and — for a
  data product — what sources go in, how they're processed, and what comes out.
  Plain language a non-technical founder/leader scans in under a minute; no
  jargon, no marketing superlatives, numbers over adjectives.
- An **architecture + data-flow diagram** (Mermaid or a committed image) near
  the top. **Cross-link** related docs so a non-technical reader can navigate.
- **Setup is one command** with minimal manual steps and an `.env.example`.
- Status is explicit (✅ live / ⏳ pending, with owner + date). Docs must match
  reality — a doc that lies is worse than a missing doc.
- **Never bake live metrics into prose** (they drift the moment they're
  written); cite the command that prints the current number instead.
- For the full onboarding method behind these non-negotiables — reader/persona
  modelling, the evaluation arc, progressive disclosure, host-native visuals,
  anti-slop craft, accuracy-vs-code, and keeping the safe install path as the
  quickstart — read `readme-authoring.md`.

## AI-facing doc (`CLAUDE.md` / `AGENTS.md`)

Written so any coding agent can pick it up and comply: the code standards, repo
conventions, how to build/test/run, the **definition of done**, and the hard
confidentiality + no-fabrication rules. It is the mechanism by which quality
survives the *next* contributor — see "Standards imprint" below.

- **Portability & interop (check for divergence).** Prefer a canonical root
  **`AGENTS.md`** (cross-vendor). Peer files — `CLAUDE.md`, `.github/copilot-
  instructions.md`, Cursor `.cursor/rules` / skills, Windsurf `.windsurf/rules`,
  `GEMINI.md`, Aider `CONVENTIONS.md` — must be **thin pointers**, not forks.
  Bridge hosts that only read another name (e.g. Claude Code → `@AGENTS.md`
  import or symlink). **If the repo already standardizes on one file, defer to
  it** and fill gaps. Two instruction files with conflicting rules is the
  finding — not which filename is "primary."
- **A standards doc is context, not enforcement.** Prose in `AGENTS.md` / peers
  guides an agent but binds nothing unless a **gate** backs it (pre-commit,
  required CI). "Documented but unenforced" is the highest-value durable-
  standards finding (see the imprint below).
- **An always-loaded rules file pays its cost every session, whether or not each section is still true.**
  Because `AGENTS.md`/`CLAUDE.md` peers load in full on every session start (not on demand like a
  skill's routed reference), they need a stricter size discipline than progressive-disclosure docs —
  one observed file grew to ~800 lines including sections describing a mechanism that had already been
  replaced same-day, still loaded on every subsequent session until someone noticed. Flag: (1) no
  stated line/size cap on the file, (2) a section describing a mechanism the repo's own history shows
  was superseded, with no corresponding deletion in the PR that superseded it. **Rule:** keep this file
  to invariants (rules that don't change per-mechanism) over mechanism descriptions where avoidable; a
  PR that retires or replaces a mechanism deletes that mechanism's section from this file in the *same*
  PR, not as follow-up cleanup.

## Developer experience

- **One-command setup**, and a **`doctor`/preflight** that names each missing
  piece with an actionable fix line, prints **no secret values**, and exits
  non-zero **only** on a genuine blocker (not on an optional key the user may
  not need).
- **Fewest commands to first run.** clone→run and clone→green-test should each be
  a single normalized command — a `script/bootstrap` + `script/test` convention,
  a `make` / `just` target, or a devcontainer — so a newcomer needs the *pattern*,
  not project-specific knowledge, to build or test. A long or undocumented
  time-to-first-run is DX friction (Info), not a defect; a **CONTRIBUTING that
  promises a workflow the scripts don't actually run** is a real finding. Watch
  **dev/prod parity** — local backing services/versions that diverge from
  production can hide correctness bugs.
- **Kit leftover vs product tree.** An `AGENTS.md` / `CLAUDE.md` that still
  describes a scaffold (`app/` + `npm start` on PORT, "you are helping a
  member build a small web app") while the repo is a real product
  (`apps/web`, `packages/*`, workspaces) is a **docs/DX defect**, not
  context. One finding: rewrite or delete the leftover so the next agent
  does not author into the wrong tree. Do not treat the leftover as the
  project's contract.
- **Local environment is part of DX, not optional colour.** The documented
  one-command path must actually bring the app up locally (or name the
  exact missing prerequisite). A README that only documents deploy, or a
  delivery overlay that never starts the stack, fails this check.
- **Document the missing-prerequisite → symptom map** for any gitignored setup:
  each absent file surfaces at a different step with an error that reads like a
  code defect. Record which absence causes which failure so each newcomer
  doesn't rediscover it. A gate that *asserts* real-data-shaped output must also be satisfiable
  from the **committed fixture**, or a "green from a clean clone" DoD claim is false even with the
  map — `testing-situational.md` (a gate's committed fixture is part of its contract).
- **An operating-discipline doc for stable environment invariants.** Beyond the
  missing-prerequisite map, an agent-driven review/delivery otherwise re-derives the
  same environment facts every cycle — how to render a reviewable / authenticated
  state, which capture tool actually works, which CI gates are conditional, known
  renderer-specific flakiness. Record these **stable invariants** once in a durable
  in-repo doc and read it **before** environment-dependent work; a fact that had to be
  **rediscovered** is a signal the doc is missing an entry, so filing that entry back
  is part of closing the task, not optional cleanup. Record only stable invariants —
  a *derived* status (an open-issue count, "the current version is X") follows **store
  the query, not the answer** (below), never a hardcoded number.
- **Single source of truth** for any cross-referenced fact (a doc index, a
  count, a schema/field list) — a pointer can't drift, a duplicate always will.
  Enforce a CI **doc↔code sync check** that fails when a tracked doc, field, or
  count drifts.
- **Dated status/handoff docs accumulate faster than anyone prunes them.** In a
  project with many contributors or agents, `STATUS-jan.md`, `HANDOFF-v2.md`,
  `HANDOFF-v3.md`-style snapshots pile up in `docs/` — each accurate the day
  it's written, stale the next, with no marker for which one is current. The
  fix is not "write a better doc": live coordination state (who owns what,
  what's blocked on whom) belongs in the issue tracker, which has native
  open/closed/assignee semantics a markdown file doesn't; at most one
  continuously-**updated** pointer doc survives in the repo, never a new dated
  file per session. Detector: `find . -iname '*status*.md' -o -iname
  '*handoff*.md' -o -iname '*progress*.md'` (excluding `node_modules`) turning
  up more than a small handful, especially with dates/version suffixes in the
  filename, is the smell; two of them asserting different values for the same
  fact (an owner, a current blocker) is proof the duplication has already
  drifted.
- **Reconcile load-bearing claims against the code.** For each doc claim using
  *optional / required / always / never / all / every*, locate the code that
  enforces it and confirm. A mismatch is a finding; a mismatch on a
  **deploy-contract** claim (what is required to run) is at least High.
- **Enumerate "lockstep surfaces"** — the sets of files that must change
  together (schema ↔ validator ↔ type ↔ prompt ↔ docs ↔ test). Misalignment
  surfaces as silent runtime breakage, not a compile error, so name them.
- **Document what is deliberately *not* tested or *not* applicable, and why**, so
  silence is never mistaken for a gap.

---

## Repository hygiene & community health

A healthy repository ships more than code. Check for the community-health files
and process controls below, but **rate each by the exposure the repo actually
has** — on a private/internal repo most are Info/Low; each escalates when the
repo is **public, distributed/packaged, or accepts outside contributions** (the
same baseline-plus-trigger logic as the `full-map.md` severity rubric). Don't emit a
wall of Mediums on a private repo — batch the Info/Low items and let the trigger
decide escalation.

- **LICENSE** — absent → legal reuse is undefined. Low for a private repo; **High
  once public or published to a package registry** (an undefined license blocks
  lawful use). OpenSSF passing criteria require a FLOSS license in a standard
  location.
- **SECURITY.md** — no vulnerability-disclosure channel. Low; Medium once public
  or externally used (OpenSSF: a project MUST publish how to report a
  vulnerability).
- **CONTRIBUTING** / **CODE_OF_CONDUCT** — Info; Low for a public project taking
  outside contributions. A CONTRIBUTING that documents a build/test flow the repo
  can't actually run is a real finding (cross-ref DX above).
- **CODEOWNERS — only as strong as its enforcing rule.** CODEOWNERS alone merely
  *requests* review; it binds a merge only when branch protection enables "require
  review from Code Owners." Present but unenforced on sensitive paths → Medium.
- **Branch protection / required checks** on the default and release branches:
  require a PR + human review + passing status checks before merge, and block
  force-push. Missing → Medium (maps to OpenSSF Scorecard *Branch-Protection* /
  *Code-Review* / *CI-Tests*); **High if unreviewed pushes reach production.**
- **CHANGELOG / release notes** — versioned releases with no human-readable change
  summary. Info; Low once consumers must track versions. Keep a Changelog:
  `CHANGELOG.md`, an `Unreleased` section, categories
  Added/Changed/Deprecated/Removed/Fixed/Security (OpenSSF: release notes MUST be
  human-readable).
- **Issue / PR templates** — `.github/ISSUE_TEMPLATE` and a PR template mirroring
  the definition of done. Info.

Do **not** re-home posture other sections already own: `.gitignore` / secret
hygiene is section N; general style consistency is section H.

**🚩**: a public repo with no LICENSE or SECURITY.md; CODEOWNERS with no "require
Code Owner review" rule; a default branch mergeable with no review or passing
checks; force-push allowed on a release branch; versioned releases with no
changelog.

---

## Standards imprint — leave the bar in place (Phase 6 of the review)

A review that only finds problems lets quality regress on the next iteration.
The highest-leverage durable output is to **persist a tailored standards set
into the reviewed project** so future contributors and agents maintain the
quality, security, safety, and efficiency bar automatically.

**This phase writes to the repository — it is opt-in and requires confirmation.**
It must be *net-positive and non-destructive* (see the "do no harm" principle in
`SKILL.md`): merge and augment, **never silently overwrite** a good existing
doc. If the project already has a standards doc or a style guide, **defer to it**
and fill gaps; if a proposed addition would substantially change existing
conventions or design, surface it as an owner decision rather than imposing it.

What to imprint (tailored to the project's actual stack and to this review's
findings — not a generic dump):

1. **AI-facing standards doc — canonical `AGENTS.md`.** Write the standards once
   in a root `AGENTS.md` (cross-vendor), and make every other agent file a **thin
   pointer** to it, not a copy: `CLAUDE.md` via `@AGENTS.md` / symlink where
   needed, plus one-line pointers for Cursor rules, Copilot instructions,
   `GEMINI.md`, Aider `read:`, Windsurf rules — whatever the repo's toolchain
   actually uses. **If the repo already standardizes on a specific agent file,
   defer to it** — fill gaps, don't relocate it. Keep the canonical file concise
   and push depth into referenced files. Contents: code standards, definition of
   done, stack-specific red flags this review surfaced, data-integrity
   invariants (if a data product), LLM-safety rules (if it calls a model), and
   the hard no-fabrication + confidentiality rules — so the *next* agent of any
   vendor complies without re-deriving them.
2. **Pre-commit / CI gates**: lint (0 warnings), format, type-check, tests, a
   **privacy/secret gate that fails closed when its banned-terms input is
   missing and reports `file:line` only — never echoing the matched secret**,
   and dependency/secret scanning. The gate scans the lines a branch *adds*; a
   green gate is a floor, not a certificate. When this skill is the source,
   `install.sh --with-gates` mechanizes a slice of this bullet directly —
   wires this skill's own `fix_class_gate.py` / `binaries_gate.py` into the
   target's CI via `scripts/dcr-gates.sh` — never a substitute for the
   stack's own lint/format/type-check/test gates.
3. **Templates**: `.env.example` (secret-free), an ADR template, a PR checklist
   mirroring the definition of done, a `.banlist.txt` seed (real identifiers go
   in a gitignored local file), and the editor/versioning conventions that keep
   diffs clean across contributors — `.editorconfig`, a `CHANGELOG.md` (Keep a
   Changelog), and Conventional Commits where releases are versioned.

**Write it safely — the imprint is idempotent and additive.** It creates, it does
not clobber: **detect and stop** if the standard already exists; **create-if-
missing, never overwrite** a good file; when touching a shared file like
`.gitignore`, **add only the missing lines** (grouped under a labeled comment),
never removing or duplicating existing entries; and **print exactly what was added
vs. already present** so the change is auditable. And remember a doc alone is
advisory — **pair each load-bearing standard with the gate that enforces it** (a
pre-commit hook / required CI check) or it will not survive the next session.

And a gate's stated **location** is a claim with its own currency: when a gate
moves — CI to local-only, one job to another, or newly hidden behind a label or
trigger — updating where it runs is part of the change, verified mechanically. A
heavy gate shifted out of CI to save cost is sound; what breaks is the paper
trail, and an agent (or a hurried human) runs what the contributor docs, PR
template, and comments *say* runs, not a re-derivation. So: **every gate names
exactly one authoritative, current location**; **audit agent-facing docs for
dangling references** — grep the contributor guide, PR template, and inline
comments for every CI job name, label, and trigger, and confirm each still exists
and still runs the gate the text claims (a reference to a job/label that no longer
fires the gate is a defect, not stale trivia); a **relocation to "local only"
makes the local bar the blocking one** (say it is required and what evidence proves
it ran — advisory-vs-trusted, #294), because a leftover "CI covers it" is an
instruction to skip the only remaining enforcement; and **fail the audit closed** —
a gate whose docs cannot be shown to name a live location is treated as unenforced
until proven otherwise. (Distinct from keeping an operating-invariants doc: that
document can exist and still name the wrong location — this is the *currency* of
the location claim. Deriving the agent-facing docs from one canonical gate
manifest — the single-source-of-truth / doc↔code-sync check above — keeps them
from dangling in the first place.)

Phase 6 imprints **this project's review bar** (`AGENTS.md`, privacy gate, PR
template). It does **not** install delivery. Delivery is a separate opt-in:
`./install.sh --with-delivery` or `--full`, after `--recommend` and an owner
yes. Mention `agentic-delivery` in the imprinted `AGENTS.md` only when that
skill is already present in the tree.

**A review-scoped rules block (optional, interop).** Beyond the all-tasks `AGENTS.md`, the
imprint can carry a **review-only** rules surface that first-party reviewers read directly, so
one imprint drives this review's pass *and* the bots. Two consumers, same idempotent-additive
discipline: a **`## Code Review Rules`** section in `AGENTS.md` (OpenAI Codex reads exactly
that — the root file is repo-wide, a nested file is service-scoped) and/or a root **`REVIEW.md`**
(Anthropic's managed GitHub Code Review reads it — severity recalibration, skip rules, a
verification bar, nit caps). Map this review's severities to the de-facto markers so the two
agree — the managed markers are coarser than the six-level rubric, so map by *is-it-a-real-bug*,
never demote a Medium to a nit: Blocker/Critical/High/**Medium** → **🔴 Important** (a Medium is
a real defect, not a style nit), Low/Nit → **🟡 Nit**, a real bug not introduced by the change →
**🟣 Pre-existing**. **State the surface split in the block**, because it bites:
the *managed* GitHub reviewer reads `REVIEW.md`, but the local `/code-review` command reads
`CLAUDE.md` only (not `REVIEW.md`) — so a rule you need on both surfaces goes in
`CLAUDE.md`/`AGENTS.md`, and `REVIEW.md` carries managed-only tuning. Author each rule in the
few-shot shape the bots parse best — *rule → bad example → good example → reasoning*, one
concern per rule.

## Persisted knowledge hygiene — store the query, not the answer

A durable doc, memory, or imprint that records a **fact derived from live state**
— an open-issue count, "the current version is X", "there are N services" — rots
the moment the state moves, and a stale fact read as current is worse than none.
When a standard or memory captures something re-derivable, **store the query, not
the answer**: the command, path, or check that regenerates the fact, so the reader
re-runs it instead of trusting a frozen number. Verify at source; the cache is a
lead, not the truth.

When a doc must state the number (a README's "N skills", "N tests"), bind it to its
counter with `scripts/derived_numbers.py`: write `<!-- derived: COUNTER ARGS -->N`
(`files GLOB`, `lines PATH`, `grep-count PATTERN PATH`, `json-len PATH KEY`) and the
gate fails when `N` differs from the counter's result; `--fix` rewrites the claim.
`scripts/dcr-gates.sh` runs it by default (`DCR_DERIVED_NUMBERS=0` turns it off).
Counters are a fixed list computed in Python, never a shell, so a doc cannot run code
in CI; paths stay inside the repo and never follow a symlink.

**Audit persisted knowledge** (a memory store, an `AGENTS.md`, a runbook) for
three decay modes — each a finding:

- **Dead paths** — a referenced file, symbol, or flag that no longer exists.
- **Status without a command** — a claim of current state ("deployed", "passing",
  "6 open") with no query to re-verify it; replace the answer with the query.
- **Embedded credentials** — a secret, token, or private identifier committed into
  the stored knowledge. This is a privacy/secret finding (cross-ref
  `privacy-compliance.md`), not a style nit.

## Spec Kit / constitution compatibility (review, do not install)

If the target already has Spec Kit artifacts — `.specify/`,
`.specify/memory/constitution.md`, or a root `constitution.md` — **review
against that constitution**. It is a durable project rulebook: every later
spec/plan/task is supposed to obey it. A review that ignores it while
walking `AGENTS.md` is incomplete.

- Load the constitution (and only that file unless a cited spec is in the
  blast radius). Treat it as a named stating artifact, same class as
  `AGENTS.md`.
- Flag drift: code or a proposed change that violates a constitution
  principle; a constitution so vague it cannot be checked; two
  constitutions that disagree.
- `--recommend` already treats `.specify` as a **live delivery pack** and
  suppresses `agentic-delivery`. Keep that. Do **not** install Spec Kit,
  do not dump `/speckit.*` commands, do not vendor the pack.
- Absence of `.specify/` is not a finding. Do not recommend Spec Kit as
  a second delivery OS.

### Minimal `AGENTS.md` skeleton to imprint (canonical — point `CLAUDE.md` and peers at it)

```markdown
# Engineering standards (AI-facing)

## What this is
<one paragraph: problem, and how it's solved — sources → processing → output>

## How to work here
- Build / test / run: <one-command each>
- Definition of done: builds; tests pass (state X/X); lint+format+type+security
  scan clean; docs updated; no dead code; every export documented + tested.
- Match the surrounding code's patterns; smallest change that is correct.

## Hard rules (never violate)
- No fabrication: skip or flag rather than guess — no invented data, sources,
  metrics, or citations. Omit any claim you can't verify.
- Confidentiality: no real names, company/team names, emails, internal IDs, or
  identifying URLs in code, comments, docs, commits, or PR bodies — including
  git history. Fictional placeholders in fixtures. Scan before every commit;
  fail closed on any hit.
- Secrets via env/secret manager only.
- Do no harm: every change is net-positive across correctness, security,
  performance, tests, docs, data quality, and accessibility — never fix one axis
  by regressing another.
- Confirm before anything destructive, irreversible, billable, or shared-state.

## Project-specific standards (from the review)
<stack-specific red flags, data invariants, LLM-safety rules, perf/cost budgets>
```

---

**🚩 red flags**: a README describing an aspirational system; stale setup steps;
undocumented env vars; no architecture diagram; "see the code for details"; live
counts hard-coded in prose; a decision with no rationale anywhere; a project with
strict standards in a contributor's head but nothing an agent can read and apply;
conflicting agent-instruction files (`CLAUDE.md` vs `AGENTS.md`); a standards doc
that no gate enforces; more than a handful of dated status/handoff/progress
snapshot docs, or two of them disagreeing on the same fact.
