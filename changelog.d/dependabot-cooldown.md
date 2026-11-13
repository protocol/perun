### Fixed
- dependabot.yml sets a 7-day cooldown so new releases are not proposed the day they ship (clears the dependabot-missing-cooldown finding). A comment in test-provision-tools.sh no longer parses as a shellcheck directive. run-ci-tests.sh and test-host-manifests.sh now exit when their initial cd fails, so they fail closed if path resolution fails.
