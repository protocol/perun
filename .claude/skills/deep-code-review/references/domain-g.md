# Domain G checklist

Read this when domain G (Concurrency & shared state) is applicable in Phase 2 — the coverage ledger marks it, or a DIFF quick-path touches it. Split from `domain-checklists.md`, whose preamble (the 🚩 convention and the language-grep pointer) applies here.

### G. Concurrency & shared state → `references/concurrency-shared-state.md`
- No data races on shared mutable state; correct locking/atomicity; no deadlock
  ordering; no check-then-act (TOCTOU). Async: awaited promises, no
  fire-and-forget that drops errors, cancellation handled.
- **Whole-file/load-once state stores**: a single writer per file (or per-key
  files) and reload-before-access, or concurrent writers clobber and long-lived
  readers never re-read; a corrupt/torn read of a critical record fails closed.
  Concurrent agents/workers **claim a lane** (the file set, with expiring claims)
  before editing and commit explicit paths — never stage-all.
- **Lifetime, not only synchronization.** A field on a long-lived singleton
  (framework `@Injectable`/`@Component`, a module global) holding per-request/run
  data leaks across calls **even with perfect synchronization** — match each
  stateful field's lifetime to its data's; thread a per-run value.
- **Race and release check (required)**: answer the three questions in `references/concurrency-shared-state.md` § Required: race and release check for every read-then-write and acquire.
- 🚩 shared mutable globals, a singleton field whose lifetime outlives its data,
  missing `await`, non-atomic read-modify-write, lock
  held across I/O, two workers writing the same file, **tests or jobs that write
  a real shared/tracked data path** (cross-ref J;
  `references/testing-and-evals.md`).
