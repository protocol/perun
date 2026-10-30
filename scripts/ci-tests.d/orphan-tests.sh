# Registers per-feature tests that existed but no CI step ran (see the "Per-PR tests" step in ci.yml; #1592 audit).
python3 scripts/test_auto_update_legacy_marker.py
python3 scripts/test_auto_update_move.py
python3 scripts/test_auto_update_stale_lock.py
python3 scripts/test_bench_corpus_90.py
python3 scripts/test_compact_mode.py
python3 scripts/test_confidence_floor_full.py
python3 scripts/test_full_audit_field.py
python3 scripts/test_small_diff_fast_path.py
python3 scripts/test_harness_friction.py
python3 scripts/test_peer_pains_5.py
