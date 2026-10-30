# Parallel / fan-out review — protocol & anti-fabrication contract

Read this when the target is large enough to review across **parallel
subagents** (a `FULL` run of a large repo, or several focused domain passes at
once), **or when reviewing how an agent *write* fan-out shapes its PRs and the CI
budget it spends** (§6). A fan-out is very effective — but without a strict contract it
manufactures plausible-but-fake findings and re-derives project context N times. Expands the
"Review mechanics" note in `SKILL.md`; it operationalizes the "a second opinion
should be decorrelated" principle at scale.

The governing fact: **subagents share the orchestrator's blind spots and carry
their own authority into the report.** Both have to be engineered against.

---

## 0. Same pinned surface for every unit

Hand every audit the Phase-0 `START_SHA` (or the dedicated worktree path at that
SHA). Resolve the **full object ID before fan-out**. A missing or mistyped requested
SHA is a hard scope failure: do not silently substitute the checked-out commit or
a unique-looking prefix and call the result exact. Correct the packet and rerun
the exact-scope unit; use abbreviated SHAs only for display after pinning the full
ID. Units read via `git show $START_SHA:path` / files in that worktree — never
"whatever is checked out now." A live tree another agent is editing will otherwise
produce disagreeing `file:line` citations and findings about code that does not
exist on the reviewed ref. If the harness cannot isolate a worktree, the lead
records that limitation and still requires every citation to resolve at
`START_SHA` on re-verify.

A shared pinned worktree is sufficient only for genuinely read-only units. Give
every unit that runs tests or builds its **own worktree/clone and per-run temp,
port, and process namespace**. Aggregate suites can write ignored fixtures, bind
fixed ports, or kill a sibling server even when tracked files stay clean. If the
harness cannot isolate executable units, run them serially and record the limit;
never interpret a concurrently contaminated failure as a candidate defect.

**A failure that only appears under heavy fan-out concurrency is contention,
not a defect, until reproduced at low concurrency.** Running many heavy
executable units (a real build, browser test, or compute process) at once can
exhaust the machine's own capacity — CPU, memory, file descriptors — and
produce timeouts or flakes indistinguishable, from inside one unit, from a
genuine defect in the code under test. This is the same "unverified until
reproduced normally" discipline the skill already applies to an
environment-shaped failure (one that appears only in a fresh worktree), applied
to a **capacity**-shaped cause instead of an environment-shaped one: before a
timeout/flake enters the findings table, re-run the specific failing check in
isolation. Cap concurrent heavy lanes per machine to a stated ceiling, distinct
from the candidate-count tiering above.

**Admission-coverage enumeration.** A shared admission primitive (slot pool, lock, semaphore) is correct only if
every entry point uses it. List every command in scripts, hooks, Makefiles, agent briefs and docs that runs a
heavy tool (test runner, build, browser, type-check); each must acquire the primitive or it is a finding (High
when reachable from an agent brief). Admission compares load to core count and waits above the threshold
rather than starting the job. Whether a hook exists is the delivery skill's concern; this is the review-time
enumeration of paths that bypass it.

**Mega-files / huge blobs:** when a single file is too large to hold in one
context (tens of KB of dense logic, generated bundles, vendored trees), split by
**named concern** (auth surface, write path, egress, parser) with overlapping
seams of ~50–100 lines so call edges are not orphaned — still one invariant per
unit. Prefer symbol/grep entry points over linear whole-file reads. Do not invent
line numbers for unread regions; unread → `unverified` or out of scope.

---

## 1. Assemble the shared context packet once, hand it to every subagent

A subagent that re-discovers the project from scratch spends most of its budget
re-reading what the lead already knows, and judges against a slightly different
bar. Assemble **one** packet (frozen schema below) and give the identical copy
to each unit.

**The packet is also a cacheable prefix — mark it as one.** A stable, reused
block handed unchanged to every unit is exactly the shape prompt/prefix caching
wants; a cached prefix is billed far below fresh input on re-send, and on a host
that supports it a cache read is routinely the single largest lever on a fan-out's
token cost — worth more than which model runs it. Assemble the packet once,
enable caching on it if the host offers the primitive, then spawn units against
the cached copy rather than re-sending it fresh per unit. Depth on this and
every other cost lever: `model-tiering.md`.

**Don't fan out at all when the work is one dependent chain or fits a single
context.** A fan-out earns its cost only when there is real bulk to split —
otherwise the plan, the handoff, and the merge it requires are pure overhead a
single pass gets for free, and on genuinely hard, non-bulk work a solo pass has
been measured to beat a coordinated fan-out outright at meaningfully lower
cost. This is the complement of section 4's stop rule: that rule says when to
stop *expanding* an already-justified fan-out; this one says when not to
*start* one — a single well-scoped `FILE`/small `DIFF` review is the common
case that should never reach for a fan-out in the first place.

### Packet schema (copy-paste; fill every field)

```
START_SHA: <sha>
WORKTREE: <path | none — citations still at START_SHA>
HARD_RULES: no fabrication; mask identifiers; read-only tools only
GATE_SCOPE: <what root gate excludes; subtree gates>
TRIAGE_HITS: <already found — deepen, do not re-report as new>
CLEARED: <paths/areas not to re-review>
ARCHETYPE: <web|api|data|agent|iac|lib|other>
AUTHZ_LEDGER: <entry points N · anon planned Y/N · two-principal Y/N>
BANNED_REMEDIES: <from Phase 0 SCOPE | NONE — do not re-propose>
REVERT_INVARIANTS: <one-line mechanism facts the reverts established — design constraints, not history | NONE>
BYTE_FIDELITY: check invisible chars before claiming string equality
LIVE_VS_PAST: git log -S before reporting "live" bugs narrated in comments
NONE_OK: empty finding list is valued
```

**Label every fact-carrying field `verified` or `to-be-verified`** (ids, targets,
counts, names, "X already does Y"): a fact is `verified` only once the lead re-read
it at `START_SHA`; unlabelled ⇒ `to-be-verified`. **Verify each lane's premise at
the pinned ref *before* dispatch** — if the entity a lane names doesn't exist
there, or a value differs from the canonical source, fix the packet before
spawning. A fan-out amplifies one wrong premise into N confident, well-cited, wrong
findings — the most expensive kind, because every anti-fabrication check passes.

**Diagnostics are per-run.** Copy any diagnostic a gate writes to a run-scoped
path the moment it is produced; a tool that writes diagnostics to a fixed global
path (`/tmp/ux-audit.json`) races other units, and on a parallel-gate project that
fixed path is itself a finding.

### Unit manifest (lead-owned; fill before spawn, update on done)

| Unit id | Invariant | Owned paths | Unit/tier actually used | Lead-read | Status |
|---|---|---|---|---|---|
| <catalog id> | <one sentence> | <paths or glob> | <requested → actual if substituted> | Y/N | planned / running / done / skipped |

Record unavailable or refused units in the **fan-out preamble** with the
**named substitute actually used** (never a silent swap). Same-tier units from
the same model family are not decorrelated second opinions.

**A stalled or missing unit is `unverified`, never silently absorbed.** A unit that
never reaches `done` (slow, capped-out, crashed, timed out, refused) does not
vanish into an implied "all clear": its owned invariant is reported `unverified`
in the Phase 5 reconciliation, named with the unit id. Fill the **Lead-read**
column as the lead's own independent read (section 4) covers each owned path, so
Phase 5 can state, per unit, **who actually covered it — finder id *and* lead-read**
— the "no silent caps" principle applied to the fan-out's own completeness, not
only to sampling inside a unit.

- **A collision check reads a PR's file list *paginated*, never `gh … --json files` (100-file
  cap).** `gh pr view/list --json files` silently truncates a PR's file list (**100 files** on the current `gh`
  client — an open client-side bug, `cli/cli#13338`, not the REST API's documented page limit) — no error, no
  warning — so a lane cleared as "no overlap" against a large in-flight PR can still collide with a
  file the capped list never showed, producing the exact concurrent-writer conflict the check exists
  to prevent. Read owned/changed paths from the paginated REST endpoint:
  `gh api repos/:owner/:repo/pulls/<n>/files --paginate --jq '.[].filename'`. Same failure class as a
  bare `gh pr/issue list` truncating to its default page (the *mind pagination* rule,
  `agentic-delivery/references/unattended-trackers.md`) and a forge-only absence check missing a
  local worktree (#413): a `gh` read returns a truncated view **without erroring**, and a partial
  read yields a wrong "safe" / "absent" conclusion — treat every `gh` read as
  **paginated-until-proven-complete** before a collision or absence verdict.
- **`gh pr edit --body`/`-b` sets the body outright — full replace, not append or merge.**
  Verified in `gh pr edit --help`: `-b, --body string  Set the new body.` (`-B/--base` and
  `--milestone` are the same single-value replace shape; the `--add-*`/`--remove-*` pairs are
  incremental, and so is `--attach` — given with no body flag it appends the image/video to the
  existing body instead of replacing it. Both `--body`/`-b` and `-F`/`--body-file` rewrite the
  body wholesale — `--body-file` only changes the input *source*, not the replace semantics, and
  is the form #739's own incident used). In a multi-lane write fan-out (§6) this clobbers two ways, both
  observed (#739): a **wrong or stale `<N>`** (a typo, or a number carried over from a sibling
  issue) silently overwrites an unrelated PR's body with no error at all; and even against the
  **right** PR, a second editor's `--body` call erases whatever the first editor wrote — a prior
  agent's checklist, review notes, or gate marker — with no diff and no merge, so a body-reading
  gate (an evidence check, a verify-marker check) then governs the wrong content and fails a lane
  nobody touched. Reviewable rule: never call `gh pr edit --body`/`--body-file` on a body you didn't just
  author — read-verify-write (`gh pr view <n> --json body`, confirm it's this PR's own content,
  re-post the **merged** text) or use a comment (`gh pr comment`) instead of a replace; a central
  orchestrator batch-editing many PRs' bodies is itself the clobber risk (single writer per PR
  body).
- **Editing `.github/workflows/*` needs the OAuth `workflow` scope — the push fails loudly, but
  only at push, after every earlier gate already went green.** Confirmed against GitHub's
  OAuth-scopes docs (`workflow`: "Grants the ability to add and update GitHub Actions workflow
  files") and reproduced (#719): a lane edited a workflow YAML, verified the change, committed
  locally — then hit `refusing to allow an OAuth App to create or update workflow <path> without
  workflow scope` at `git push`, because the token carried `gist, read:org, repo` but not
  `workflow`. A subagent cannot self-heal this (granting the scope needs the human's browser
  device-auth), so it blocks a whole **class** of lanes — any workflow-editing lane — and a fleet
  that dispatches several before checking wastes each one identically. One trap inside the trap:
  a workflow file identical in path *and* contents to one already committed on another branch can
  push without the scope, so a single past green push is not proof the scope exists. Reviewable
  rule: before dispatching a lane that touches `.github/workflows/`, check `gh auth status` for
  `workflow` in the token's scopes (fix once, interactively: `gh auth refresh --scopes
  repo,workflow,read:org,gist`); route workflow-editing lanes separately from app/tooling lanes so
  a missing scope fails closed on only the CI slice, and bank a blocked lane's already-good local
  commit rather than rebuild it once the scope lands.

### Invariant catalog (pick one per unit — do not invent overlapping "find issues")

| Unit id | Invariant (one sentence) |
|---|---|
| anon-GET | Every documented GET refuses sensitive bodies without auth |
| IDOR | Two-principal object-swap: other→403/404, none→401 |
| dual-surface | Every caller of a sensitive loader enforces the same authz/redaction |
| cache-authz | Identity-derived responses not publicly cached at CDN/origin |
| injection | No string-built SQL/command/HTML sinks on untrusted input |
| spend-cap | Every paid call is behind a pre-call cap (default 0 = no cap = finding) |
| monotonic | No write path lowers a populated/higher-confidence field |
| gate-exclude | Gate-excluded subtrees are named and audited or flagged |
| fail-closed | Security/config absent or empty → refuse, never pass |

Then give each subagent only its **unique scope + one catalog id**. This pays the
domain-context duplication once instead of once per unit.

### Tier the sweep — cheap enumerate, then expensive confirm

One monolithic high-effort finder per domain makes total agent-minutes scale with
**domain size**, not defect count: two large surfaces then hold the whole pipeline
under a small concurrency cap while clean domains sit queued behind them. Split the
fan-out into two tiers so cost tracks **candidate count** instead:

- **Tier 1 — candidate sweep (fast, low-effort).** One cheap pass per unit that
  only *enumerates* candidate invariant violations (`file:line` + a one-line
  claim), no deep proof. A clean domain then costs one cheap sweep, not fifteen
  minutes of deep reading.
- **Tier 2 — confirm (high-effort).** Runs **only on the candidates that survive
  Tier 1**, plus the adversarial re-verify of section 4. High-effort minutes are
  now proportional to surviving candidates, so the fan-out degrades gracefully
  under a small cap.

**Size units small — one invariant, a few hundred lines of owned surface.** A unit
that owns a 500-line file plus its tests is the one that stalls; keep the
one-invariant-per-unit split the catalog already prefers, sized so no single finder
holds more than a few hundred lines of owned surface (mega-files still split by
named concern per section 0). Record the tier each unit actually ran in the
manifest's *Unit/tier actually used* column.

**Tier by model capability too, not only by effort.** Run Tier 1 on a fast/cheap
model, promote only survivors to Tier 2 on a mid/frontier model, and reserve the
strongest tier for the lead's own re-verify (section 4) and any candidate that could
become Blocker/Critical — the escalate-on-failure cost lever (same pass rate for
roughly half the cost, with the vendor-neutral tier definitions) lives in
`model-tiering.md`; this section applies it to *model choice* as it already does to
*depth of pass*.

---

## 2. Read-only by toolset, not only by instruction

Review is read-only (principle 7). Fan-out units must not be able to mutate the
reviewed project just because the prompt said "don't edit."

- **Prefer a harness-enforced read-only tool allowlist:** Read / Grep / Glob /
  `git show` / `git log` / `git grep` (and similarly non-mutating inspect). No
  Edit, Write, apply-patch, or mutating shell (`git commit`, `git push`,
  `git checkout`, `git reset`, `rm`, redirects that overwrite project files).
- **If the harness cannot restrict tools,** the prompt must **forbid all mutating
  commands explicitly**, and the lead **snapshots the tree before fan-out**
  (`git status --porcelain` + `git rev-parse HEAD`) and **diffs after**. Any
  unexpected change → hard-fail the fan-out, restore from `START_SHA` /
  worktree, and discard that unit's unverified output until re-run read-only.
  **The tree diff is blind to anything outside the tree** — it proves no
  tracked file changed and proves nothing about an issue filed, a comment
  posted, a message sent, or any other forge/API call a unit's tools can
  reach. Where a unit has network or forge-CLI access, the read-only
  contract has to be enforced or checked at that boundary too (a scoped
  token, a disabled `gh`/API credential, or a post-hoc audit of the unit's
  actual tool calls) — a clean git diff after a run that had `gh`/API access
  is evidence about the tree, not about the unit's full action.
- **Context-inheriting forks are especially dangerous, and stripping the
  prompt is only half the mitigation.** Strip unrelated parent instructions
  ("open a PR", "commit this", "file issues for what you find") from the
  unit prompt; give only the packet + one invariant. Then **verify the strip
  held** — a fork that inherited "file issues for what you find" earlier in
  the session and was later given a narrower "return a table, create
  nothing" can still act on the wider, older instruction it never
  forgot; the narrowing is a new instruction competing with an old one, not
  a guaranteed overwrite. Check what the unit actually called (its tool-use
  log, not its own summary) before trusting that a read-only or
  narrowed-scope fork stayed inside scope.

### Harness notes (map the allowlist; do not pretend every host enforces it)

State in the fan-out preamble which case you are in. Prompt-only "don't edit"
is never enough by itself. **Contract is host-neutral** — only the spawn
mechanism changes.

| Host / pattern | How to get read-only audits | Fallback when you cannot |
|---|---|---|
| **Generic / any agent** | Spawn or hand off with an explicit tool allowlist: Read / Grep / Glob / non-mutating git only. Pass identical packet + `START_SHA` + one invariant. | Mutate-ban in prompt + lead before/after `git status` / `HEAD` diff; hard-fail on drift. Prefer a dedicated worktree the unit cannot push from. |
| **Cursor** (Task / subagents / skills) | Skills under `.cursor/skills/` or `.agents/skills/` (also loads `.claude/skills/` / `.codex/skills/`). Restrict tools when the Task UI offers it; otherwise treat as unrestricted. | Same tree-diff hard-fail. |
| **Claude Code** (subagents / Task) | Prefer a subagent/tool allowlist with no Edit/Write. Slash-invoke `/deep-code-review` when installed under `.claude/skills/`. | Mutate-ban + tree-diff. |
| **Codex** | May load `.codex/skills/` or follow `AGENTS.md`. Assume full Edit/Write/shell unless sandboxed. | Mutate-ban + tree-diff; worktree. |
| **Copilot / Gemini / Aider / Windsurf** | Usually instruction-file driven (`AGENTS.md`, copilot-instructions, `GEMINI.md`, `.windsurf/rules`). No reliable tool lockdown — sequential in-process invariants under principle 7, or external read-only checkout. | Same. |
| **One-shot paste** (no subagents) | No fan-out — run invariants sequentially in-process under principle 7. | N/A |

If the host documents a "read-only" / "ask" / "plan" mode, use it for audit
units and still re-verify at `START_SHA` — mode labels are not evidence.

### Specialized-subagent quirks → never stall security

Some hosts ship **rigid specialized reviewers** (fixed-prompt units that accept
only a repo path + diff selector and refuse a free-form A01 / domain audit).
**Harness ceremony must not delay the security pass.**

| Situation | Action |
|---|---|
| Specialized reviewer rejects / ignores a domain-invariant prompt | Retry **immediately** with a **general-purpose** (or equivalent unconstrained) unit under the **same** read-only contract + shared packet + one named invariant. |
| Specialized reviewer only accepts "branch changes" / "uncommitted changes" | Use it for that shape; run domain A01/authz as a separate generalPurpose unit — do not skip A01 waiting for the specialty harness. |
| Specialty unit unavailable / times out | Same fallback: generalPurpose, read-only, re-verify at `START_SHA`. |

Record the fallback in the fan-out preamble ("specialty rejected → generalPurpose"
or "requested unit unavailable → <named substitute>") so the lead knows the unit
was not the decorrelated specialty reviewer — still re-verify; never drop A01
because the host's named security agent was picky. Never silently swap models.

---

## 3. The fabrication-resistant subagent contract

Put every clause in each subagent's prompt. A clean large tree will otherwise
hand back a hundred confident inventions.

- **One named invariant per unit**, not "find problems in domain X." ("No
  update path can lower a populated field." "Every paid call is behind a
  pre-call cap.") A unit hunting a specific invariant reports real breaks; a unit
  told to "look for issues" fabricates to look thorough.
- **A finding requires `file:line` + the concrete failing input/state**, and that
  `file:line` must resolve at `START_SHA`. No failing case → not a finding. Ban
  severity words without a reproduction.
- **`NONE` is a correct, expected, valued answer.** Say so explicitly, or the
  unit invents an issue rather than return empty.
- **A packet fact is a hypothesis until you read it at `START_SHA`; contradicting
  it is first-class output.** If the entity the packet names does not exist, or a
  value differs from the canonical source, report `BRIEF_CONTRADICTION: <asserted>
  | <found at file:line@START_SHA> | <what I'd have written if I'd trusted it>`
  **first, and stop** — do not substitute a nearby entity or soften it to a caveat.
  A unit that returns only a contradiction has done its job.
- **Cap findings (~5)** and **prefer running a probe over speculating** — a
  five-line script that proves the break is worth more than a paragraph of
  "this could…". Probes that need a planted defect run only in the lead's
  dedicated worktree (Phase 1), never in a shared live tree.
- **Mask real identifiers in the unit's own output** before returning to the
  lead: emails, people/company names, internal IDs, hostnames, secret-shaped
  strings → role placeholders or redacted forms (`j***e@e***.com`). Fan-out is
  how PII otherwise reaches the lead's context and the report. Do not echo
  secret values even redacted if a fingerprint/`file:line` suffices.
- **Return an affirmative `checked_sound` list, not only findings.** For each
  invariant the unit opened the code and confirmed *holds*, record it with the
  same `file:line`-or-drop rigor a defect gets — `invariant | file:line@START_SHA
  | what proves it`. Say this list is a valued, expected product: on a hardened
  target the finding list is empty and `checked_sound` is the unit's **entire**
  output, so the unit affirms specific soundness ("tenant selection is
  JWT-`sub`-only; body/query/header cannot select a tenant") instead of inventing
  a defect to look thorough. An affirmative claim must be as falsifiable as a
  defect claim — the lead re-verifies it (section 4), and it is the primary
  deliverable on a hardened target (SKILL Phase 5, "Invariants verified to hold").

---

## 4. The orchestrator re-verifies every survivor — in both directions

No subagent finding enters the report on the subagent's authority. For each
survivor the lead **re-opens `file:line` at `START_SHA` and confirms against
source, adversarially** — and verification runs **two ways**:

- **Refute false positives.** Try to break the claim; a finding that can't be
  reproduced at source is dropped, not softened. A citation that only exists on
  another branch / dirty tree is contamination — exclude it.
- **Test whether a `NONE`/caveat understated a gap.** A unit that returned
  "NONE, minor caveat" may have missed that the caveat *is* the finding.
  Verification catches **under**-reports, not only over-reports.

**Check the finding against the tests before `CONFIRMED` — re-reading the source
the finder read cannot catch an intended-behavior false positive.** The source
looks exactly as the finder (and a source-only verifier) described it; only the
**tests and the suite encode intent**, so a verify stage that just re-reads source
inherits the finder's blind spot. Before any `CONFIRMED` verdict, do at least one
of:
- **Test-awareness (minimum).** Locate and read the tests that exercise the
  finding's file/function. A finding whose proposed fix would **contradict an
  existing passing assertion** is `REFUTED` — the behavior is intended by design,
  not a defect — unless you can show the test itself is wrong (say why, in
  writing). `REFUTED` drops the finding; it never enters the report.
- **Fix-against-suite (gold standard; required when the finding proposes a code
  change to security / cost / concurrency logic).** Apply the proposed fix in a
  **throwaway worktree** (never the shared tree — principle 7) and run the repo's
  own gates, then **discard the worktree and confirm it is gone** (the disposal every
  principle-7 probe owes). A fix that turns the suite **red** refutes the finding, or proves it
  needs a different fix; a fix that keeps the suite green and reproduces the
  original break red-first is the strongest `CONFIRMED` a fan-out can produce.

**Confidence marker on every finding** (surface it in the report):
- `CONFIRMED` — the lead independently re-verified it at `file:line` on
  `START_SHA`.
- `CORROBORATED` — two or more independent audit units (different invariants /
  angles) hit the same sink or defect class; still lead-re-verify before it
  blocks a gate, but treat convergence as a stronger signal than either alone.
- `PLAUSIBLE` — subagent-reported, not yet lead-verified. A sibling of the
  `unverified` convention; **never silently promoted** to a bare finding.

**Preserve material dissent.** When unit A reports `NONE` and unit B confirms a
finding on the same sink (or they disagree on severity/reachability), keep both
claims in the lead notes until source re-verify decides. Do **not** majority-
collapse; record which unit the lead favored and why.

**Re-verification is symmetric, and a brief contradiction never majority-
collapses.** When a unit's *measurement* contradicts the lead's *diagnosis*, the
lead verifies the measurement — a hypothesis carries no evidentiary weight against
an instrument reading, and a review that never corrects its own lead is not being
verified. One unit contradicting the packet outweighs nine succeeding on it (the
nine answered a question the tenth just showed was wrong): re-verify at source,
correct the packet, and re-run any unit whose invariant depended on the bad fact.

**Affirmative `checked_sound` claims are re-verified too.** A unit's "this
invariant holds" entries carry the unit's authority exactly as findings do; the
lead re-opens the load-bearing ones at `file:line`@`START_SHA` and drops any that
don't hold. An unverified "invariant holds" is as misleading as an unverified
defect — and on a hardened target it *is* the deliverable (SKILL Phase 5,
"Invariants verified to hold"), so it earns the same file:line-or-drop rigor.

**The lead reads the top-N blast-radius files independently — concurrently with
the fan-out, not post-hoc.** When there are **zero survivors** (the common outcome
on a hardened target, where finders return `[]` and re-verify has nothing to chew
on), the review's credibility rests entirely on the lead's own reading — so make
it explicit and non-empty. While units run, the lead reads the top-N
highest-blast-radius files (N sized to the target; Phase 0's triage already ranks
blast radius) adversarially and independently. This (a) gives a **non-empty
confidence basis on a clean target**, (b) cross-checks the finders' `[]` returns
against a second independent read, and (c) means a slow or stalled fan-out never
leaves the highest-stakes surfaces unread. Record it in the manifest's **Lead-read**
column; Phase 5 reports lead-read coverage alongside finder coverage.

**Stop rule.** Stop expanding fan-out when high-blast sinks already have two
independent passes plus lead re-verify at `START_SHA` — more units on a settled
sink is theater, not coverage.

**This re-verify duty generalizes past findings — to any lane's causal claim an
orchestrator acts on.** A lane's self-report about *why* something failed or
succeeded (a misattributed regression, "this isn't a real bug," "this is now
fixed") carries the same no-authority-on-its-own-say rule as a finding above
(principle 2, `full-map.md`). Before dispatching further work, closing an
investigation, or merging on the strength of that claim, the conductor (or a
human reviewer) checks the actual evidence the claim rests on — the real test
output, the real CI log, an actual reproduction — never the lane's summary of
it; independently re-running the same check the lane claims to have run, from
the evidence it cites, is the bar (mirrors the fix-against-suite gold standard
above, applied to a claim instead of a finding). **A gate passed via a
documented escape hatch or override flag is a distinct, lower-trust status,
never folded into an undifferentiated "passed."** Any report of a gate passing
must state explicitly whether an override/escape-hatch was used to get there;
a conductor treats an override-flagged pass as `PLAUSIBLE`, not `CONFIRMED` —
re-verify it before it blocks or clears a gate the same as any other
unverified claim. Grep merged reports for override/escape-hatch flag usage and
confirm each one is disclosed, not silently absorbed into "passed," as a
standing audit habit.

---

## 5. Subagents inherit the reviewer's blind spots — inject the discriminators

A tool that renders bytes, a repo that documents its own past, and a grep that
matches dead code fool every unit the same way. Put these discriminators in
**every** subagent prompt, and have the orchestrator apply them to
security-critical claims itself:

- **Byte-fidelity** (cross-ref principle 2, domains C & R): the viewer may
  collapse NUL / zero-width / bidi / BOM to whitespace or drop them. Any finding
  that hinges on an invisible or easily-confused character — "this delimiter is
  absent," "this comment is stale," "these two strings differ" — is checked at
  the byte level (`xxd` / `od` / a code-point dump) before it is asserted, and
  treated as `unverified` until then. This kills false "stale comment" findings
  **and** catches real invisible-character injection the render hides.
- **Live defect vs documented past one** (cross-ref Phase 4): comments often
  narrate fixed incidents in present tense (`Audit 2026-…`, `Bug B`, `live
  incident …`). Before reporting, apply Phase 4's live-vs-historical
  discriminator (`method.md`) — a fan-out will otherwise re-report the repo's own
  changelog as new bugs, once per unit. Pair with Phase 0's **measured** history
  depth — do not argue from a README claim that history is absent.
- **Grep hit vs the surface that actually runs** (cross-ref principle 9,
  root-cause-not-symptom): a string match is a *candidate*, not a confirmed live
  site. The file may not be on the reviewed route's render or execution path at
  all — a component never mounted on the screen in question, a handler wired to
  nothing, dead code kept for history. Before a finding (or a fix) names a
  `file:line` as *the* live surface, trace it: for a UI, route → component tree to
  confirm the component renders on that screen; for a code path, the call graph
  from a real entry point to confirm it executes. `git grep` / symbol search finds
  candidates; the render or call trace confirms. A fix aimed at a grep hit the
  target never runs is wasted work that also leaves the real surface — the one
  that does render — still broken. The lead applies this to any finding whose
  severity rests on the cited line being live.

---

## 6. Budget the CI a fan-out triggers — one reviewable PR per concern, staged gates

A write fan-out that opens **many small PRs**, each re-triggering the **full**
browser / a11y / e2e matrix, multiplies shared runner minutes without improving
review — the same matrix runs N times on work one PR would have reviewed once. On a
repo with a shared GitHub Actions (or equivalent) budget, that is a **cost defect in
the fan-out's *shape***, reported **once** with a remedy — not one finding per PR (the
*batch routine cleanup as one finding* discipline, `branch-and-merge-hygiene.md` §7):

- **Prefer one reviewable PR per concern** over many fragment PRs. Work that only
  makes sense reviewed together is one PR; splitting it to parallelize writers just
  multiplies CI with no review gain. (The security/permission/authz diff still rides
  its **own** small PR for a decorrelated reviewer — Delivery, below — a *review*
  split, not a budget one.)
- **Keep draft iteration on a cheap, path-filtered gate;** reserve the expensive
  **browser / a11y / e2e matrices** for a readiness signal — a `full-ci` label, manual
  dispatch, or the final pre-merge gate — not every push to every draft.
- **Cancel superseded runs** with a concurrency group keyed by PR/ref, so a new push
  does not leave its predecessor's full matrix running. **But the cancel race cuts both
  ways:** under rapid successive pushes the run for the **final** head can be cancelled as
  a superseded sibling (or never created), leaving the newest SHA with **no run at all** —
  not a failure, an **absent** check. Two wrong reads follow, and they are **not symmetric**: a strict gate merely refuses a branch that is actually fine (safe but noisy); **worse**, a human sees the last green (belonging to an earlier, since-cancelled head) and merges believing the final head passed — a silent **fail-open** merge of an unverified head. Before
  trusting or merging, confirm a run **exists and concluded for the exact head SHA** —
  never infer from "the branch has a recent green"; treat "no run for this SHA" as a
  third state (not passed, not failed → re-dispatch a run for this head, then decide), matching the required-check-must-report discipline in `merge-operations.md`. Reduce the race
  at source: scope cancel-in-progress so it never cancels the newest run. That silent fail-open merge is a merge-safety defect, **not** this cost section’s default Medium: its severity is inherited from the unverified head it lands, not from runner cost.
- **A merge guard must not render a `CANCELLED` run as a *failure* — that fails closed on a green
  head.** The mirror of the fail-open read above: a guard that buckets `CANCELLED` (a superseded /
  concurrency-cancelled run) with `FAILURE` **blocks a genuinely-mergeable PR** as red. Distinguish
  **four** states per required check — `PASS`, `FAIL`, `PENDING`/`IN-PROGRESS`, and `NO-RUN` — and
  treat `CANCELLED` as a subset of **PENDING** (transient: re-dispatch or wait for the live run),
  never as `FAIL`. Select the run **deterministically — latest per check *name* at the exact head
  SHA** — group the runs by check name at that SHA, then take the one with the latest
  **completion time**, never "latest by creation order" (which can return the cancelled sibling). In the status table, `PENDING` /
  `CANCELLED` must read as visually distinct from `FAIL` — a `CANCELLED` row rendered red is the
  defect.
- **Path filters must fail closed.** A filter that **skips** a gate on an
  *unrecognized* path silently drops it — a **gate exclusion**, and a path filter is
  exactly the config `method.md`'s *enumerate what the gates exclude* rule tells you to
  audit separately; its correctness severity is inherited from there, not from this
  cost section. **Privacy and security checks are never path-filtered out**, on any
  path.
- **Keep a documented one-command local full suite,** and require the **labelled full
  run** before merging an app change — the cheap gate speeds iteration without becoming
  the merge bar.
- **Before a fix lane pushes, list the CI jobs its diff will fire.** Run
  `python3 .claude/skills/deep-code-review/scripts/ci_cost_advisor.py <repo-dir> --diff <base>`,
  with `<base>` the branch the PR targets, such as `origin/development`: `branches:` filters are
  matched against it, and a sha or tag base tags each job such a filter gates
  `(branches: unchecked)`. Every `pull_request` job the committed diff triggers (path filters
  applied) prints with its `run:` lines; a job that builds an image, starts containers or has
  `services:` is tagged `[runtime]`. Workflows on `push`, `merge_group` or `workflow_run` are only
  named. Run each listed job locally, or name it `left to CI` under the PR body's `How to verify`;
  a green unit run proves nothing about a `[runtime]` job, so a Dockerfile-only fix can pass every
  local test and still break the image job.
- **One canonical path→gate manifest when more than one surface routes by path.** CI `paths:`
  filters, a pre-push/pre-commit hook's file scoping, and the local suite's "which gates for
  which files" each encode the *same* **path→required-gates** map (which globs are gated areas and
  the full gate-set each needs); hand-maintained in parallel they **drift** — a path gated in CI
  but not the hook (or the reverse) silently skips its gate on one surface. Keep that map in
  **one** version-controlled manifest and have every surface **derive** its routing from it, with
  a **CI drift-gate** that fails when any surface's routing no longer matches the manifest — the
  repo's own single-source-of-truth rule (`docs-and-dx.md`) applied to gate routing. Each surface
  still runs its own stage-appropriate **slice** (the cheap hook need not run CI's full matrix,
  per the staged-gate bullet above); what must not drift is *which paths map to which gates*. An
  unrecognized path resolves to the **full** gate set (fail closed, above), never to "no gate". A
  drift that drops a **security/privacy or correctness** gate on any surface inherits its severity
  from the gate-coverage / confidentiality canon (like the fail-open filter above), **not** this
  cost section's *Medium at most*; the pure cost/DX residue is Medium.

**State the residual risk — not optional.** Staged CI trades **coverage for cost**:
the cheap path-filtered gate **will not catch browser-only regressions** until the
local or labelled full run executes. A staged-CI recommendation that does **not name
the uncovered regression class** is incomplete — an unrun matrix is `unverified`, not a
pass (`full-map.md` principle 2: an absence is evidence only after a positive control
fires).

**Severity.** The wasted-runner-minutes cost is **Medium at most**, batched as one
finding with the staged-pattern remedy. The **fail-open path filter** and a
**path-filtered-out security check** are separate findings carrying their own, higher
severity from the gate-coverage and confidentiality canon — not from this cost section.
Signals: many fragment PRs each triggering the full matrix; a path filter that skips
(not fails) on an unknown path; a privacy/security check behind a path filter; a "green
CI" claim resting on a draft gate that never ran the browser matrix; the same path→gate
map hand-maintained in more than one surface (CI / hook / local) with no single manifest
they derive from.

---

**Delivery:** when a fan-out yields both routine fixes and a change to a
security/permission/authz boundary, split the remediation by risk surface (see
`SKILL.md` Phase 5) — the security-critical diff rides its own small PR for a
decorrelated reviewer, never buried under nits. Report files follow Phase 5's
shared-tree escape hatch.


### Dedupe across lanes before synthesis, and default a FULL review of an agent-layer service to four domain lanes

Overlapping High findings from several lanes cost tokens in synthesis, so run one shared dedup step (merge by location and root cause) before the orchestrator re-verifies. For a FULL review of a service with an agent layer, four domain lanes (security, AI, cost, privacy/CI) are a good default: one field run produced five High findings across them with little overlap. Also require the review prompt to list every call site of a changed pattern, each marked covered or uncovered, and a per-diff independent review pass before hand-off.
