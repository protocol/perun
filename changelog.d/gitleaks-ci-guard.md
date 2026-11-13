### Added
- CI now runs scripts/test_gitleaks_allowlist.sh in a `gitleaks` job (full-history checkout, gitleaks 8.30.1 installed from its release tarball with the sha256 checksum file verified, REQUIRE_GITLEAKS=1), and the `gates` aggregate requires it. Before this no workflow called the script.
