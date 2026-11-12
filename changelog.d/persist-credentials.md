### Fixed
- Every actions/checkout step in ci.yml and release.yml now sets `persist-credentials: false` (zizmor artipacked): no later step pushes or fetches a private ref, and gh uses GH_TOKEN from env. scripts/test_workflow_persist_credentials.py, registered in scripts/ci-tests.d, fails any new checkout that omits it unless the step carries a `zizmor: ignore[artipacked]` reason.
- The test also takes a directory argument and can scan the shipped workflow templates; the dcr-gates.yml template checkout still lacks `persist-credentials: false` (follow-up, needs a skills-tree edit).
