# Shell / Bash red flags

Read this when the target runs any shell — CI `run:` steps, hooks, Dockerfile `RUN` lines, Makefile recipes, or shell scripts (reviewed code — the reviewer's own verification-shell hazards stay in the parent). Split from `language-stack-redflags.md`; its fast first pass and cross-language sections apply to every review, and each hit here is a signal, not a verdict.


- Unquoted expansions (`rm -rf $DIR`), `eval`, `curl … | bash`, parsing `ls`,
  missing `set -euo pipefail`, secrets in `set -x` traces, world-writable temp.
- `for x in $LIST` as a membership/exclusion check on an **unquoted** variable —
  bash word-splits it, zsh (default) does not, so a safety-critical skip/exclusion
  list silently stops excluding under the wrong shell. Use `case` or a line-based
  `grep -qxF`; full mechanism + the merge-guard instance:
  `merge-operations.md`.
- **`set -u` + `"${arr[@]}"` on an *empty* array is a fatal `unbound variable`
  under bash 3.2 — still macOS's default `/bin/bash` (verified `3.2.57`).** A
  script that conditionally builds an array (flags, a discovered file list,
  cleanup targets) and expands it under `set -u` aborts the instant the array is
  empty; this most often sits in **trap / cleanup / reporting** code on the error
  path, where it **masks the real failure** it was meant to report. Guard the
  expansion (`${arr[@]+"${arr[@]}"}`) or seed the array — and run the script
  against the **actual `/bin/bash` on the target**, since a dev box's
  newer/homebrew bash can behave differently and hide it.
- **A bracket *range* used to VALIDATE a character class — `case $x in *[!0-9a-f]*)`,
  `[[ $x =~ ^[0-9a-f]+$ ]]`, `grep '[0-9a-f]'` — is resolved against the locale's
  collating sequence, not codepoint order, so the *same* script returns a *different*
  verdict under a different `LC_COLLATE`.** POSIX defines a range expression as "the set
  of collating elements that fall between two elements in the collation sequence,
  inclusive" and warns that "in other locales" (than POSIX/C) "a range expression has
  unspecified behavior" (The Open Group Base Specifications, RE Bracket Expression). On
  an implementation that collates in dictionary order under a UTF-8 locale (GNU/glibc:
  `a A b B … z Z`), the uppercase letters sort *inside* `[a-f]`/`[a-z]`, so a guard meant
  to *reject* anything that is not lowercase hex (`*[!0-9a-f]*`) silently *accepts* an
  uppercase digest; under `LC_ALL=C` (byte order) the same guard is strict and rejects
  it. The leniency is a property of the **locale + collation data, not the OS** — a
  C/POSIX locale, or any libc that collates these ASCII ranges by codepoint, is strict,
  so do not key the risk to a platform ("macOS is lenient"); verify the target's
  `LC_ALL`/`LANG`. Consequence: a pre-commit hook that blocks every local commit on one
  developer's box while CI stays green, or the reverse — a lenient local pass a strict CI
  rejects — from a **byte-identical** script run in two locales. **Fix:** pin `LC_ALL=C`
  for the comparison, or drop the range for an explicit enumerated set
  (`*[!0123456789abcdef]*`); a POSIX named class (`[[:xdigit:]]`, `[[:lower:]]`) reads the
  intent but is itself locale-scoped, so a security/gate comparison should still pin
  `LC_ALL=C`. **Grep lead:** a bracket *range* (`[a-f]`, `[0-9a-f]`, `[A-Z]`, `[a-z]`)
  inside a `case` / `[[ =~ ]]` / `grep` used as a validity check with no `LC_ALL=C` in
  scope — read whether the compared value can carry the boundary case (uppercase where
  lowercase is meant). **Discriminator vs the gate-divergence family:** the *drifted local
  gate copy* false-green (`merge-operations.md` § "Self-reported evidence is not a
  trusted control") is two scripts that **differ** — a stale vendored paste behind the CI
  definition — fixed by *single-sourcing* the logic; here the script is single-sourced and
  **byte-identical**, and single-sourcing does **not** fix it: only pinning `LC_ALL=C` (or
  an explicit set) stops one file being read two ways. Distinct too from the
  changed-files / fetch-by-ref detective control and the extension-allow-list
  under-coverage gate in `reliability-error-handling.md` (which turn on *which* input the
  gate sees, not on how one input is interpreted), and from the application-text collation
  rules in `i18n-l10n.md` (sorting / case-folding *user data* for display — this is
  collation inside a *gate's control flow*).
- **A GNU-only flag piped to `2>/dev/null` in a liveness/idle check fails open, silently, fleet-wide
  (#1158).** A relative-time `find` probe (`-newermt`, or `-printf`) only GNU findutils accepts; BSD/macOS
  `find` rejects it as a bad option, and stderr piped to `/dev/null` "to keep output clean" swallows that
  invalid-option error along with the noise it was meant to suppress. The command then matches nothing,
  and every worker reads idle — including ones that just wrote output — because the failure looks like "no
  match," not "the check itself is broken." The same shape recurs with GNU coreutils' `stat -c`/`--format`
  (BSD/macOS `stat` uses `-f`), `date -d`/`--date` (BSD/macOS `date` has no `-d`; use `-j -f` to parse or
  `-v` to adjust), and `sed -i` given **no** argument (BSD/macOS `sed -i` requires one, even an empty
  string, `sed -i '' ...`; GNU's suffix is optional, `-i[SUFFIX]`) — each pair verified from the platform's
  own man page and the GNU manual (`docs/standards-index.md`, 2026-09-24). **Never suppress the stderr of a
  check whose result drives an action** (kill, restart, reassign, alert, "report idle"): if the command can
  fail for a reason other than "no match," that failure must be visible or explicitly handled, not
  discarded. Prefer the portable form both implementations accept (a numeric "N minutes ago" `find` flag
  over a relative-date string only one parses) or detect the platform and branch, and smoke-test a
  liveness/staleness probe against one known-live and one known-idle subject **on the actual target
  platform**, not only the one it was authored on. Mechanized by `scripts/reaper_lint.py`'s
  `GNU_FLAG_SILENCED_STDERR` rule (concurrency-shared-state.md routes the rest of that script).
- **`env NAME=value -u OTHER cmd` fails loudly on BSD/macOS `env`, and that's the trap.** BSD/macOS `env`
  stops parsing options at the first `NAME=value`; an option (`-u`, `-i`, `-S`) placed after one is read
  as the wrapped utility's own name instead — verified on macOS: `env A=1 -u B true` prints `env: -u: No
  such file or directory` and exits 127. Some implementations (e.g. GNU `env`) accept the interleave, so
  the script that was authored and tested there runs clean and only breaks when it ships to a BSD/macOS
  box. Options first, every time: `env -u B A=1 cmd`. Mechanized by `scripts/reaper_lint.py`'s
  `ENV_OPTION_AFTER_ASSIGNMENT` rule. The error is loud but easy to miss when the command boots a
  backgrounded child: it lands in the child's own log while the harness reports only a readiness timeout.
  A harness that boots a child must fail fast on the child's early exit and print its log tail.
- **A gate that calls a Linux-only tool turns red on macOS for a check that never ran.** `setsid`,
  `flock`, `timeout` and `/proc` paths are absent from a stock macOS install (checked on macOS 26; other
  BSDs are not guaranteed to have them), so a gate script that calls one exits 127 or reads nothing
  there and posts FAIL for a check that never ran, and every developer on a Mac sees a red gate that is
  not a finding. Probe first (`command -v <tool>`, or `uname`) and report the check
  as **not run** when the tool is absent, never as failed or passed. Mechanized by `scripts/reaper_lint.py`'s
  `LINUX_ONLY_NO_PREFLIGHT` rule.
- **A script that gates on another tool's log, not its exit status.** Gate on
  the tool's exit status, captured to a file — never a pipe (pipe-hides-exit-code
  hazard: `language-stack-redflags.md`'s verification-shell section); the
  mechanized form is `templates/pre-push-verify.sh`, which decides only on the
  captured command's exit code and never greps a log. Suites rerun at every gate
  stage: `scripts/gate_map.py` reports the repeats, `scripts/gate_cache.py` is the shared
  tree-keyed PASS cache. If a log must still be
  parsed, anchor on the runner's own summary line, copied from a **real passing
  run** — never written from memory: a bare `PASSED`/`FAILED` word also matches
  test *names*, so a failing run can quote a green test's name as its evidence.
  Dry-run the check against one known-green and one known-red log before it
  runs unattended. The last line is an explicit positive result; its absence is
  failure.

- **A gate piped to `tail`/`head`/`grep` masks its exit code, and doctrine alone did not stop the recurrence** (two branches reported pushed after failing a pre-push gate). The operating layer ships a `PreToolUse` Bash hook, `agentic-delivery/scripts/pipe_mask_guard.py`, that warns (or blocks with `PIPE_MASK_MODE=block`) on a gate/push/merge piped to `tail`/`head`/`grep` without `pipefail` or `PIPESTATUS`.

- **Copy-paste commands in docs, briefs and skill files are executed as typed, in the reader's interactive shell.**
  Treat every fenced shell block in Markdown as a command run in the default interactive shell (zsh on macOS) and
  in bash, and check both. An unbraced `$name` followed by `:` or other punctuation must be `${name}`, for example
  `git push origin ${b}:${b}`. A variable-built refspec or destination is shown by a dry run (`echo` or
  `--dry-run`) before the mutating command in the same block. Mechanise as a grep over fenced blocks in `*.md`
  for an unbraced variable followed by `:`; Low, or High when the block pushes, deletes or deploys. This rule
  pins the form, not a specific zsh expansion mechanism.
