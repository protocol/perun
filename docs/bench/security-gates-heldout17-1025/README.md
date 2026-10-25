# Held-out 17 (authored 2026-10-25, blind; not scored)

Seventeenth held-out security-gates corpus, harder than held-out 16. Authored blind: no guard source, test, scorer, rival code, or other corpus rows were read (only the format of held-out 16). Not scored; no results claimed.

Files: `destructive-dangerous.txt` (60 rows) and `destructive-benign.txt` (60 rows), one shell command per line. Rows are never executed. Hosts and names are fictional (example.com, Acme).

Dangerous rows are evasion-heavy destructive commands an agent must not run unasked: indirection via env vars, aliases, functions, arrays, eval/printf builders, base64 and heredoc into a shell, xargs/find -exec/-delete, python/node/perl/ruby one-liners doing rm/rmtree/unlink, quoting and escaping tricks, command chains and subshells, git clean/reset/force-push variants, dd/mkfs/truncate, and cloud/k8s/DB destructive CLIs. Benign rows are near-twins that look scary but are safe: echo or grep of the string, comments, dry-runs, --help, scratch and build dirs, read-only cloud/k8s/git commands.

Integrity: `SHA256-frozen.txt` holds the corpus hashes; `ledger.jsonl` records the preregistration with the sha256 of `SHA256-frozen.txt`.
