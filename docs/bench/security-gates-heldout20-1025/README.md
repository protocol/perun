# Destructive-command corpus held-out-20, 2026-10-25

Blind authored corpus for the destructive-command guard. Written without reading the guard, its tests or rival ports. Format matches docs/bench/security-gates-1024: one command per line, `#` lines are comments, plain text, no IDs.

| File | Contents |
|---|---|
| destructive-dangerous.txt | 60 dangerous commands: shells, cloud CLIs (aws, gcloud, az), databases, disks, git, containers, kubernetes, terraform/pulumi, interpreter one-liners, base64/quote/escape obfuscation |
| destructive-benign.txt | 59 safe look-alikes developers really run (cleanup of build dirs, read-only cloud and DB queries, scoped git and docker commands) |

All names are fictional (Acme, example.com). No secrets. No row is ever executed; rows are only classified as strings. Score by running the guard's check function over each row (blocked dangerous / flagged benign), as score.py in security-gates-1024 does.

Hashes are in SHA256-frozen.txt (`shasum -a 256` of the two corpus files); ledger.jsonl holds the preregistration event hashing that file. Freeze before any tool runs on the corpus.
