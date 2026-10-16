# Focus kit: handoff, memory hygiene and a docs map

Read this when a session runs long or compacts, a new session must resume the work, or memory files
and docs grow faster than anyone prunes them. It applies `project-state.md` (what a checkpoint holds)
and `operating-discipline.md` (the `handoff_inject.py` re-inject) with one stdlib script and adds no
second todo list: the owner's asks stay in the task ledger (`agentic-ceo`, `scripts/task_ledger.py`).

Every command is `python3 .claude/skills/agentic-delivery/scripts/focus_kit.py <command>`.

## What survives a reset

Verified 2026-10-16 from the Claude Code memory and context-window pages (in the standards index):
- Project-root `CLAUDE.md` is re-read from disk after `/compact`; an instruction given only in
  conversation is lost.
- Auto memory: the first 200 lines or 25KB of `MEMORY.md` load at session start; topic files load
  only when read.
- A SessionStart hook on `compact|startup|clear` can add text to the new context: `handoff_inject.py`
  does, at most 2KB, and on `startup` it skips a handoff older than 24h.

State that must outlive a reset therefore lives in a short file the host or a hook reloads whole.

## Handoff: `.claude/handoff.md`

Keep it untracked (add it to `.gitignore`): session state, not history, one continuously updated
file and never a dated copy per session (the `deep-code-review` skill's `docs-and-dx.md` lists that
pile-up as a red flag). `templates/handoff.md` holds the sections (Goal, Stage, Next 3 steps, In flight,
Blockers / owner asks, Decisions). Change one section in place; the first call creates the file:

    focus_kit.py handoff set next - <<'EOF'
    1. rerun the failing gate
    2. open the PR
    3. ask the owner about X
    EOF
    focus_kit.py handoff add decisions "chose A over B: cheaper to undo"

A section is named by its heading, any case, a unique prefix is enough (`next`, `in flight`).
Other sections stay byte-identical; only the `Updated:` date is re-stamped. A result over 1900 bytes
is refused with a per-section size list, because `handoff_inject.py` injects 2048 bytes in total and
would cut the tail. Decisions come last since they only grow. One call replaces a Read plus an Edit.

**Update it** at each milestone (a gate passes or fails, a lane returns a receipt or blocks, a PR
opens or merges, the owner changes the goal); before a context-heavy step (a fan-out, a large read,
a long test or build, anything likely to trigger auto-compact); before handback or ending the
session. `context_nudge.py` prints this command once the context passes 250k tokens; the other
moments rest on this rule. One writer, the Conductor: a lane reports through its receipt, and owner
asks stay in the ledger (cite `T-###`, never copy the list). The one-line file that
`lane_guard.py wait --progress FILE` overwrites says a lane is alive, not what to do next; it is
liveness, never a handoff.

**Resume a new session:** read `.claude/handoff.md` and `docs/INDEX.md`, run `task_ledger.py status`
when the ledger is installed, then open only the doc whose row matches. A handoff older than 24h is not injected at `startup`
(a staleness guard, not a deletion): read it by hand when the work continues.

## Memory hygiene: `memory-lint [DIR]`

Report only: it prints findings and never writes, renames or deletes; the agent or owner decides.
`DIR` defaults to the host's auto-memory dir for this repo (`~/.claude/projects/<project>/memory/`).
It also checks the always-loaded `CLAUDE.md` and `AGENTS.md`.
- One fact per file, named for the fact. Flags: `file-big` (over 3KB), `multi-topic` (3 or more
  headings), `near-duplicate`.
- The index is one line per file, `- [Title](file.md) — hook`, at most 150 characters, at most 150
  lines and 20KB (the host drops what follows line 200 or byte 25KB). Flags: `index-line-long`,
  `index-lines`, `index-bytes`, `index-dangling`, `index-dup-link`, `index-dup-title`, `orphan`.
- A fact that can rot carries its date; `stale-date` flags a file whose newest date is older than
  `--stale-days` (default 30). `path-gone` and `flag-gone` flag a path, or a `--flag` of a script, that
  the file names and that no longer exists. A derived status (a count, "the current version") is not a
  memory: store the command that computes it.
- The always-loaded layer stays under 200 lines (~10KB): the host's own target and
  `cost-quality-guardrails.md` section 7. Move detail into docs that a trigger routes to.

## Docs map: `docs-index [--check]`

Writes `docs/INDEX.md`, one `| file | read this when | tok |` row per doc, cut like the skill
`INDEX.md` files. A row is the doc's H1 title plus its own opening: a YAML `description:`, else a
paragraph starting "Read this when", else its first sentence, so open each doc with the line that
says when to read it. `--exclude DIR` leaves bulk data out and the header records it. Run
`docs-index --check` in CI so the map cannot go stale, and link it once from `CLAUDE.md`.

## Measure

`focus_kit.py measure` prints the bytes an agent reads to recover state: everything (CLAUDE.md,
AGENTS.md, every doc) against the injected handoff plus the index. It is arithmetic on current file
sizes, so rerun it instead of quoting a number.
