# Code structure — boundaries, coupling & the cost of change (domain H)

Read this when the review judges module boundaries or coupling: a FULL review of a codebase that has grown past one module, a diff that adds a module, package or dependency edge, a refactor or "split this" request, or the question is how to make code cheaper to change, faster to build, or faster to start. The design questions (boundaries and seams, dependency direction, state ownership, failure-domain isolation, evolvability) are in `role-coverage.md` (section "Architect — architecture quality"); this file adds the deterministic probes and the structure-to-speed links, and does not restate those questions.

ISO/IEC 25010:2023 splits maintainability into modularity, reusability, analysability, modifiability and testability. The probes below measure modularity and modifiability directly; testability is `domain-j.md`.

## Run the probes (read-only; install nothing in the target)

Use only a tool the target already has installed or configured. Otherwise use the language-neutral probes and say the tool was absent: review is read-only (principle 7 in `SKILL.md`), and an `npx` or `pip install` of an analyser runs third-party code.

1. **Import cycles and layer rules.** Tools named on their project pages (2026-10-16): madge `--circular` (JavaScript: AMD, CommonJS, ES modules), dependency-cruiser (JavaScript and TypeScript; forbidden-dependency rules, circular dependencies, orphans), Import Linter (Python; constraints on imports between modules), ArchUnit (Java; dependencies between packages and classes, layers and slices, cyclic dependencies, run as plain unit tests). If the target configures none, the finding is that its architecture rules are convention, not a gate (a standard with no enforcing gate is advisory, `docs-and-dx.md`). If it configures one, read what the rules permit: a rule set that allows every exception proves nothing.
2. **Fan-in and fan-out.** Count distinct importing files per module (`rg -l` on the module's import path) and distinct modules each file imports. High fan-in marks a stable core, where a change is expensive and the module should stay small, tested and dependency-light. High fan-out marks orchestration, which should stay thin. A module high on both and near the top of the churn ranking in `domain-h.md` (the hotspot lens) is the god module.
3. **Co-change coupling** (coupling the import graph cannot see: files that change together across a boundary):

```
git log --no-merges --since='6 months ago' --name-only --format='tformat:@@' |
awk -v max=30 '
  function flush(  i, j) { if (n > 1 && n <= max) for (i = 0; i < n; i++) for (j = i + 1; j < n; j++) print f[i] "\t" f[j]; n = 0 }
  /^@@/ { flush(); next }
  NF { f[n++] = $0 }
  END { flush() }
' | sort | uniq -c | sort -rn | head -20
```

Commits with more than `max` files are skipped as bulk changes. The output is a lead list, not a verdict. Lockstep surfaces (a version stamp, a generated checksum, a changelog) rank first by design and are expected (`domain-h.md`, lockstep surfaces). The lead is a pair in different modules with a high count and no import edge: a missing abstraction or an undocumented contract. It needs real history; a shallow clone yields nothing, so say so (`HISTORY_DEPTH` in the first-response block).

## Structure that costs speed (measure before claiming a number)

- **Import-time work.** A module that does I/O, builds large tables or starts clients at import time slows every start: a CLI, a test run, a serverless cold start. Python reports it: `python -X importtime -c 'import pkg'` prints cumulative and self time per import (added in Python 3.7). 🚩 a network or disk call, a `connect()` or heavy computation at module top level.
- **Bundle shape (JavaScript).** Tree shaking relies on the static structure of ES module syntax. Webpack's `sideEffects` property in `package.json` says which files are safe to prune when their exports are unused, a re-export file or an import kept for its side effect (a polyfill, a stylesheet) can change what stays in the bundle, and a wrong `sideEffects: false` drops code that was needed (webpack documentation). Read the route's real bundle report instead of assuming. The bundle-size budget rule is in `concurrency-shared-state.md`.
- **Hot and cold paths.** Keep rarely used code (admin screens, export, importers) off the request and startup path with lazy loading or separate entry points; the UI side is `web-render.md`.
- **Pure core, effects at the edge.** Pure functions can be cached, run in parallel and pinned by tests before a speed-up, which makes optimisation safe. I/O threaded through the middle of the logic blocks all of that. 🚩 a pricing or scoring function that reads the clock, the database and the network inline.
- **Data access scattered across layers.** It hides N+1 and blocks batching; centralise the access, then batch (`performance-db-cost.md`).
- **Build graph.** In a bundled or compiled build a change to a module invalidates what depends on it, so a high-fan-in module that changes often keeps builds near-full. Check the build tool's dependency graph or cache hit rate before blaming the machine (`delivery-speed.md`).

## Scalability and capacity (routed, not restated)

How the structure behaves at ten times the load is `role-coverage.md` (Architect: scaling posture and single points of failure) and `concurrency-shared-state.md` (section "Measure before optimizing: per-section time under load, and scalability audits by dimension").

## What not to flag

- Layers or abstractions for a small codebase. Three similar lines beat a wrong abstraction (`domain-h.md`), and an early-stage project's deliberate internal modularity inside one deployable is correct (`infra-evolution-by-stage.md`).
- A cycle between two files of one module that always change together is cheap; a cycle across packages is the finding.
- Structural findings are Medium or Low unless they cause a defect. A redesign is an owner decision under Decisions needed, never a Blocker (principle 5 in `SKILL.md`, `role-coverage.md`).

**🚩**: an import cycle across packages; a `utils` or `common` module whose fan-in grows with every feature; two directories that change together in most commits with no import edge; tests that import another module's internals; a module with import-time side effects; layer rules that exist only in a document.
