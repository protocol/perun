### Changed
- The guard timing check in `scripts/test_security_gates_corpus.py` is now a scaling check (25KB vs 2.5KB, best of 3, fail above 30x) with a loose 1 s ceiling, so CI noise no longer trips an absolute 100 ms cap while quadratic code still fails.
