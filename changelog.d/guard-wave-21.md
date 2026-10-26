### Added
- Destructive guard wave 21: every review-2 finding. Pins in `scripts/test_destructive_guard_w21.py`.
- Cypher: an operand tested both null and not null through `NOT`, parentheses, a wrapping function (`toString(n.x)`) or `exists(n.x)` is an always-true WHERE; `all|any|none|single(x IN [..] ...)` over a list literal, `id(n) = id(n)`, `id(n) IS NOT NULL`, `size|length|coalesce(..) >= 0` or `IS NOT NULL` are constants; a nested `WHERE` inside a function call no longer counts as the outer filter; `MATCH ((n))` is the bare pattern.
- Cypher false positives closed: `id(n)`/`elementId(n)` against a constant, `size(n.tags) = 0`, `length(n.name) > 3`, `coalesce(n.deleted,false)`, `exists(n.tmp)`, `NOT exists((n)--())` and `1 IN n.ids` are filters; `<literal> IN` is a constant only before a list literal.
- Size cap (65536 characters or 2000 lines, fail closed) no longer counts the body of a heredoc fed to a plain `cat [>file]`, `tee [-a] file` or `git commit -F -`; a heredoc fed to a shell or interpreter, an unterminated one, and an unquoted one whose body expands `$(` or backticks still count.
- `sed|perl -i` of `sshd_config` is blocked when `PermitRootLogin` and `PasswordAuthentication` are edited by two separate commands in one line (`&&`, `;`, `|`, newline).
- `find /etc/<app> -exec chmod go-rwx` is allowed again for app directories; system-owned `/etc` children (`passwd`, `shadow`, `pam.d`, `ssl`, `ld.so*`, `sudoers*`, `systemd`, and similar) stay blocked.
- Reading stdin no longer hangs when it is a terminal.

Review round 2 (same wave):
- Cypher: `id(n)`/`elementId(n)` is a filter only when compared (`=`, `<`, `>`, `IN [..]`, `IN $p`) to a short literal or parameter; `IS NOT NULL`, self-compare, `<> ''`, `STARTS WITH ''`, negative or huge constants and `IN range(` are tautologies again.
- Cypher WHERE is read per branch: a branch is unfiltered only when every `AND` term is a tautology (`id(n) IS NOT NULL AND n.k=1` is allowed), a null pair counts only when it is the whole OR branch, `NOT ( ... )` around a null pair is refused, and `any(x IN [1,2] WHERE x = n.k)` is a filter (only an empty list literal is vacuous).
- Unquoted heredoc bodies (any command, any size) have their `$( ... )` and backtick substitutions vetted as commands, including `$\<newline>(`; quoted tags (`<<'EOF'`, `<<"EOF"`) stay inert.
- The split sshd_config check is tokenised: `sed|perl -i` or `ex` as the command word, a file argument ending `sshd_config` or an `sshd_*` glob, a value `no`, root-login keyword in one edit and `Password*`, `KbdInteractive*` or `ChallengeResponse*` in another. Setting `yes`, `prohibit-password`, quoted or `git log --grep` text and `sshd_config_x` are allowed.
- A 10,000,000-character hard ceiling applies even to data heredocs.

Skipped: `cat -n <<'EOF'`, `echo hi; cat >f <<'EOF'`, `cat >f 2>&1 <<'EOF'`, CRLF and `git commit -m x -F -` big bodies still fail closed (safe false positives).

Review round 3 (same wave), redesign to fail closed:
- Cypher WHERE is an allowlist. It filters only when every OR branch is an AND of `v.prop OP literal|$param`, `v.prop STARTS WITH|ENDS WITH|CONTAINS|IN ...`, `v:Label`, `v.prop IS [NOT] NULL`, `id(v)|elementId(v) = literal|$param` or `IN [list]|$param`, or a pattern predicate such as `(n)--()`, and no operand is tested both null and not null. Any `NOT`, any other function, constant-vs-constant term, `id()` range or property-vs-property comparison blocks the delete. This blocks again several deletes base allowed: `size(n.tags) = 0`, `length(n.name) > 3`, `coalesce(..)`, `exists(..)`, `NOT exists((n)--())`, `id(n) >= 100`, `1 IN n.ids`, `any(x IN l WHERE ..)`, `n.a IS NULL AND n.b=1 OR n.a IS NOT NULL AND n.b=2`; rewrite them as `v.prop OP literal` or as separate statements.
- Unquoted heredoc: from every unescaped `$(` or backtick, the text to the end of the body is vetted as a command (no paren matching); more than 32 substitutions blocks; an odd run of backslashes before `$(` or a backtick makes it literal text.
- The split sshd_config check is quote-aware (`;`, `|` inside a quoted sed, ex or perl script stay in their command), covers `sshd_config.d/*`, and matches keyword prefixes (`Permit`, `Root`, `Pass`, `Kbd`, `ChallengeResponse`).

Review round 4 (same wave):
- Cypher allowlist: a pattern predicate with a variable-length `*` is refused (`(n)-[*0..]-()` matches `n` itself); an operand with an `IS NULL` branch refuses any other OR branch on that operand; complementary comparisons of one operand and literal (`=`/`<>`, `<`/`>=`, `>`/`<=`) and a term next to its own `NOT` are refused. Widened: `NOT` before a non-null term or pattern, `$p.x`, exponents, `- 1`, doubled quotes, nested `n.a.b`; whitespace and comments are normalised before the clause split (`STARTS  WITH`). The block message now lists the allowed grammar. `n.k IN [1,2] OR n.k IS NULL` is blocked (split it into two statements).
- sshd_config split: skips `VAR=val`, shell keywords and `sudo|doas|env|nohup|xargs` with options; covers `gsed` and `awk -i inplace`; `\t`/`\s` before `no`; keywords anchored to `PermitRootLogin` and `PasswordAuthentication|KbdInteractiveAuthentication|ChallengeResponseAuthentication` (abbreviated keywords such as `s/Permit.*/` are no longer read).
- Heredoc substitutions: counted as substitutions (a backtick pair is one), cap 64; each is vetted up to its quote- and comment-aware close, or to the end of the body when no close is found or the text holds `case`; prose after a `$(date)` is no longer read as a command.

## Review round 4 (same wave)

Grammar shrunk instead of chasing spellings.

- Cypher `DETACH DELETE ... WHERE` is a filter only when it has no `NOT` (except `IS NOT NULL`), no `XOR`, and no two OR branches that touch the same operand (compared with whitespace removed). Newly blocked: `NOT n:Foo`, `NOT (n)--()`, `n.a = 1 AND NOT n.b = 2`, `n.a = 1 OR n.a = 2`, `n.id = 1 OR n.id = 2` (use `IN [..]`). Complement checks no longer run across AND terms, so string ranges such as `n.ts >= "2024" AND n.ts < "2025"` are allowed again. Literals ignore whitespace (`- 1`).
- Unquoted heredoc command substitutions are vetted from each substitution start to the end of the body (fail closed, cap 64; a backtick pair counts once, and `$(` inside backticks no longer resets state). Newly blocked: a body such as `$(date)` followed by a line `rm -rf /`.
- sshd lockout: any command with `sed|gsed|perl|awk|gawk|ex|vim|vi|ed` as a word and an `sshd_config`/`sshd_config.d/*` word is treated as an edit, with no wrapper list; `ed` heredoc bodies are read; shell comments are no longer stripped when tokenising.

## Wall-clock cap

- The check runs in a forked child; the parent kills it and blocks (exit 2) after 10 seconds, so a hook that spins in a regex or waits on input ends on its own instead of running for hours. A child that crashes or dies on a signal, a parent stopped by SIGTERM, and any uncaught error or exit code other than 0 or 2 also block; a failed fork falls back to vetting in-process. Pinned in `scripts/test_destructive_guard_w21.py`.
