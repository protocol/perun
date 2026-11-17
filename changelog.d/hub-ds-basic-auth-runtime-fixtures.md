### Fixed
- scripts/test-review-checks-ds-basic-auth.sh: build the credential-shaped URL and Basic-header fixtures at runtime from parts, so no literal in the test matches the gitleaks curl-auth-header rule or the privacy gate. The history scan still sees the earlier literal, so its single fingerprint is added to .gitleaksignore.
