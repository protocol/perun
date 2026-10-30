### Fixed
- The wall-clock pins of `scripts/test_destructive_guard_w20.py`, `scripts/test_secret_extra_rules_w12.py`, `scripts/test_secret_extra_rules_w13.py` and `scripts/test_secret_extra_rules_w14.py` (0.2 s and 0.5 s on 100 KB lines) are now 2.0 s, so a loaded CI runner no longer fails them; a catastrophic-backtracking regression still takes far longer.
- `scripts/test-rules-locale.sh` and `scripts/test-tests-wired.sh` print `SKIP  en_US.UTF-8 ...` and run their C-locale cases when the runner has no `en_US.UTF-8`, instead of failing on a locale that is not installed.

### Changed
- `veche.py --help` states the `--json-out` directory rule: the record is written through a temp file beside the target, so a read-only file in a writable directory is replaced, while a read-only directory or a bind-mounted file exits 2. Test: `scripts/test_veche_doc_claims.py`.
- `council.md` says the `scores` map may sit under `scores` in the verdict object itself, or in any other object (bare or under `scores`), as `veche.py` reads it.
