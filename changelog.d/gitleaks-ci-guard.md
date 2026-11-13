### Added
- CI now runs scripts/test_gitleaks_allowlist.sh in a `gitleaks` job (full-history checkout, gitleaks 8.30.1 installed from its release tarball verified against a hardcoded sha256, REQUIRE_GITLEAKS=1), and the `gates` aggregate requires it. Before this no workflow called the script.
- The guard is strict (missing gitleaks or shallow history FAILs) only when REQUIRE_GITLEAKS=1 is set, so the per-PR test legs, which do not install gitleaks, SKIP it.
