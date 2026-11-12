### Added
- `review_checks.sh` tool hub routes `staticcheck` (Go, whole module with `GOPROXY=off GOTOOLCHAIN=local GOFLAGS=-mod=readonly GOWORK=off`, NDJSON diagnostics; exit 1 with no output is `not run`, exit 0 with no output is the only clean case), `NOT CHECKED` when the tool, `go.mod` or `go` is missing; `provision_tools.sh` lists it (brew). `tool-hub.md` records why cosign, trufflehog filesystem, semgrep `p/secrets`, poutine and oxlint are not routed; sources fetched 2026-11-12 in `docs/standards-index.md`.

### Fixed
- kube-score objects with `checks: null` (a manifest with nothing scorable) no longer turn the whole run into `not run`.
- Tests: the tflint stub derives its filename from `--chdir` and `--filter` (a `sub/b.tf` row is asserted), and empty stdout with exit 0, 1 and 2 is `not run` for kube-score and tflint.
- size-budget-raise: .claude/skills/deep-code-review/references/tool-hub.md 33563→35282 staticcheck row, cosign/poutine/oxlint not-routed reasons, tflint filename and plugin notes
- Tool hub: staticcheck and the ZAP report treat whitespace-only output as empty (not run, never clean), and a staticcheck `compile` diagnostic (a package failed to load) is not run.
