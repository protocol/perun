### Fixed
- CI pins `pyyaml==6.0.3` next to hypothesis: the `scripts/test_workflow_persist_credentials.py` guard fails closed without it, so the runner no longer depends on whatever PyYAML the image ships.
