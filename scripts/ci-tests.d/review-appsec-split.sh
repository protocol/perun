# Registers the security-appsec.md core split: every pre-split line survives in the parent or appsec-egress.md / appsec-flows.md / appsec-corroboration.md, each routed with a trigger, parent size capped (see the "Per-PR tests" step in ci.yml). Offline.
python3 scripts/test_appsec_split.py
