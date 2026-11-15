Tool hub: verify snyk-agent-scan and keep it route-only

Upstream (PyPI and GitHub, fetched 2026-11-15) shows Apache-2.0, version 0.6.11, a required SNYK_TOKEN and calls to the Agent Scan API, with no documented offline mode. The hub therefore never runs it; tool-hub.md states the verified reason and a new offline test asserts it is not invoked and emits no finding rows even with SNYK_TOKEN set.

size-budget-raise: .claude/skills/deep-code-review/references/tool-hub.md 59805→59884 snyk-agent-scan row states the verified key and network requirement
