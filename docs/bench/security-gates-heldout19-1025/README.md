# Held-out 19 (authored 2026-10-25, blind; not scored)

Nineteenth held-out destructive-command-guard corpus. Authored blind: no guard source, test, scorer, or earlier corpus rows were read (only the file layout of held-out 18). Not scored; no results claimed.

Files: `destructive-dangerous.txt` (60 rows) and `destructive-benign.txt` (60 rows), one single-line shell command per line. Rows are never executed. Hosts and names are fictional (example.com, acme).

Dangerous rows: data loss, system damage, credential wipe, force history rewrite, remote infra deletion, disk wipes, with evasion via variables, subshells, base64/eval, aliases, interpreters, xargs/find, rsync --delete, mv of system dirs, wrappers, and cloud, k8s, terraform, docker and database CLIs. Benign rows: look-alikes that are safe (in-tree build cleanup, mktemp cleanup, topic-branch push, named test containers, dry-runs, echo/comments, read-only queries).

Integrity: `SHA256-frozen.txt` holds the corpus hashes; `ledger.jsonl` records the preregistration with the sha256 of `SHA256-frozen.txt`.

## Scoring

Corpus files are unchanged from the preregistered copy (`SHA256-frozen.txt`, `ledger.jsonl`); no hash amendment. 60 dangerous and 60 benign rows (59 benign commands).

This corpus was blind at scoring: the destructive guard at guard wave 13 (7ed6e90bf) blocked 58 of 60 dangerous commands and flagged 9 of 59 benign. Misses: `cat /dev/zero > /dev/sda` (a redirect was only checked against system files, not raw disks) and `kubectl delete -f - <<< "$(kubectl get all -o yaml)"` (a manifest from stdin cannot be vetted).

Follow-up (wave 14): a write to a raw disk (`>`, `>>`, `tee`, `cp`/`mv`/`install` destination) is blocked; `kubectl delete -f -` is blocked unless it is a `--dry-run`. Known gaps closed in the same wave: `mv` brace expansion (`mv /{etc,tmp} x`), `--target-directory=`/`-tDIR` destinations, and `~/../../etc` or `$HOME/../..` sources. Five false positives are allowed, each on a narrow rule: `rm -rf "$(git rev-parse --show-toplevel)/out"` (a repo-root child among disposable build directories, git not redefined), `td=$(mktemp -d) && ... && rm -rf "$td"` (variable set once from `mktemp -d`, never reassigned, sole `rm` operand), `find . -name node_modules -type d -prune -exec rm -rf {} +` (exact cache directory names only), `mkfs.ext4 ./disk.img` (a relative `*.img|*.raw` file, no `ln -s` in the command), and `psql -h localhost -d acme_test -c 'DROP TABLE IF EXISTS tmp_import'` (local host, a database named `test`, `tmp` or ending `_test`/`_tmp`, one DROP/TRUNCATE TABLE, no other options or `PG*` environment prefix).

Four false positives are deliberately kept: `docker volume rm acme_test_data` (the daemon may be remote via `DOCKER_HOST`/context, and a name is not proof of scratch data), `helm uninstall acme-pr-42 -n acme-preview` (the kube context may be production), `dropdb --if-exists acme_test_tmp` (no explicit host, so `PGHOST` may point anywhere), and `redis-cli -h localhost -n 15 FLUSHDB` (localhost can be a port-forward to a shared server and no name distinguishes it). In-sample score is 60/60 blocked and 4/59 benign flagged. Pin and probes: `scripts/test_security_gates_heldout19_blind.py`.
