# Destructive-command corpus held-out-20, 2026-10-25

Blind authored corpus for the destructive-command guard. Written without reading the guard, its tests or rival ports. Format matches docs/bench/security-gates-1024: one command per line, `#` lines are comments, plain text, no IDs.

| File | Contents |
|---|---|
| destructive-dangerous.txt | 60 dangerous commands: shells, cloud CLIs (aws, gcloud, az), databases, disks, git, containers, kubernetes, terraform/pulumi, interpreter one-liners, base64/quote/escape obfuscation |
| destructive-benign.txt | 59 safe look-alikes developers really run (cleanup of build dirs, read-only cloud and DB queries, scoped git and docker commands) |

All names are fictional (Acme, example.com). No secrets. No row is ever executed; rows are only classified as strings. Score by running the guard's check function over each row (blocked dangerous / flagged benign), as score.py in security-gates-1024 does.

Hashes are in SHA256-frozen.txt (`shasum -a 256` of the two corpus files); ledger.jsonl holds the preregistration event hashing that file. Freeze before any tool runs on the corpus.

## Scoring

Corpus files are unchanged from the preregistered copy (`SHA256-frozen.txt`, `ledger.jsonl`); no hash amendment. 60 dangerous and 59 benign commands.

This corpus was blind at scoring: the destructive guard at guard wave 14 (d9afb72b3) blocked 58 of 60 dangerous commands and flagged 0 of 59 benign. Misses: `$(printf 'rm\x20-rf\x20/')` (a command substitution used as the command word runs its escape-decoded output) and `crontab -r` (deletes every scheduled job).

Follow-up (wave 15): a statement whose command word is a `$(...)` or backtick substitution is judged like `eval $(...)` (decoders and printf/echo escapes are blocked, plain output is checked as a command), also behind `VAR=x`, `sudo`, `&&`, `;`, `then`/`do`; a variable set from a decoding or escaped substitution and then run as the command word is blocked; `$'\x72\x6d'` ANSI-C words are decoded before the check; `crontab -r` in any flag form (`-ir`, `-ri`, `-u USER -r`) and `crontab /dev/null` are blocked while `-l`, `-e`, `-i` and `crontab -l | crontab -` stay allowed. In-sample score is 60/60 blocked and 0/59 benign flagged. Pin and probes: `scripts/test_security_gates_heldout20_blind.py`.
