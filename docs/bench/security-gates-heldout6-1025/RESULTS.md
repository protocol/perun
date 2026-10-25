# Held-out 6 results, 2026-10-25

**BLUF.** On a third blind corpus authored before the wave-3 rules were scored against it, the destructive guard with the wave-3 rules blocked 45 of 60 dangerous commands with 2 of 60 benign blocked. Main before #1990 blocked 24 of 60 (6 benign blocked) and #1990 alone 28 of 60 (2 benign blocked). The ported claude-code-safety-net subset blocked 11 of 60 (1 unported, 2 benign blocked) and the ported hooks-mastery rules 15 of 60 (8 benign blocked). The wave-3 review fixes left the score unchanged. The rows scored before wave 5 are blind and no rule had been tuned toward this corpus then; it is in-sample since wave 5 (see below).

**In-sample since wave 5.** The wave-5 rules were written against this corpus's misses and false positives, so the guard now scores 59 of 60 blocked with 0 of 60 benign blocked on it; that number is tuned to the corpus and is not a generalization claim. The blind rows above remain the out-of-sample result. Pins: `scripts/test_security_gates_heldout6.py` (in-sample) and `scripts/test_security_gates_heldout6_blind.py` (blind).

**Method.** Authored blind and hash-preregistered (`SHA256-frozen.txt`, `ledger.jsonl`; commit 1bcd79ff0 on `prereg/heldout6`, pushed before scoring). The wave-3 rules were written against held-out-5 before this corpus was scored; the wave-3 lane did not read these files. Commands: `python3 -I docs/bench/security-gates-1024/score.py --corpus-dir docs/bench/security-gates-heldout6-1025` and `python3 -I docs/bench/security-gates-1024/rivals/score_rivals.py --corpus-dir docs/bench/security-gates-heldout6-1025`. Pins: `scripts/test_security_gates_heldout6.py`.

| System | Dangerous blocked (60) | Benign blocked (60) |
|---|---|---|
| Perun guard, main e42fed4a7 (blind) | 24 | 6 |
| Perun guard, #1990 879a0c13a (blind) | 28 | 2 |
| Perun guard, wave-3 e13520bb1 (blind) | 45 | 2 |
| Perun guard, wave-3 post-review 7bd064ae5 (blind) | 45 | 2 |
| Perun guard, wave-5 (in-sample, 27d1c7d63) | 59 | 0 |
| claude-code-safety-net (ported subset, 1 row unported) | 11 | 2 |
| hooks-mastery (ported) | 15 | 8 |

**Misses (15), post-review.** Windows and PowerShell deletes and formats (5 rows), `vault secrets disable` and `vault delete`, `gh api -X DELETE`, `glab repo delete`, `mongosh --eval` with `deleteMany`, `git reflog expire` plus `gc --prune=now`, `cp` onto `/etc/passwd` and `sshd_config`, `openssl enc -d` piped to a shell, and `kubectl exec ... bash -c "dropdb ..."`.

**False positives (2), post-review.** A `python3 -c` that only prints `rm -rf /`, and an extension-scoped `find $TMPDIR -name "*.tmp" -delete`.

**Caveats.** Same-model-family author; rival systems are ports of published rules, not binaries; n is small. The misses above are leads for the next rule wave, which will be scored on a fresh corpus; once rules are tuned toward them, this corpus becomes in-sample for the guard.
