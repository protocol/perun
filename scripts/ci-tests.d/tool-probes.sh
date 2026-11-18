# Fails when an installed external tool yields 0 rows on its seeded fixture, or when no tool was probed at all; a missing tool is NOT RUN, never a pass.
bash scripts/test-tool-probes.sh
