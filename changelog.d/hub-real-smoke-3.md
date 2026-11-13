### Changed
- The real-hub CI job now also installs pinned, checksum-verified real zizmor, gosec, staticcheck, kube-linter, flawfinder and detect-secrets (all offline, no advisory database) and asserts each is reported as ran with its expected rule id on a fictional canary file, so a changed flag or report shape in these six scanners fails CI instead of passing on stubs alone.
