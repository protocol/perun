# Exposed debug/management surface rules in inventory.yml: seeded bad fixtures (recall 100%) and env-gated clean twins (0 hits); live part SKIPs without semgrep.
command -v semgrep >/dev/null || unset REQUIRE_SEMGREP # absent semgrep SKIPs here; the real-hub job runs this test with REQUIRE_SEMGREP=1 itself
python3 -I scripts/test_semgrep_inventory.py
