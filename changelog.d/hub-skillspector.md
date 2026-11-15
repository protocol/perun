Tool hub: route NVIDIA SkillSpector through review_checks.sh

Adds skillspector (changed SKILL.md files, one per run, `--no-llm` static analysis, SARIF to a file). It is NOT CHECKED when missing, and not run on a crash, empty or wrong-shape output, or a non-zero exit with no row. Cisco mcp-scanner is documented as not routed: its raw output schema and the offline behavior of config scans are not documented, so no row was added.

The SARIF location shape and single-file SARIF output of skillspector are unverified against a real binary and marked so in tool-hub.md; the new test uses a stub binary.

size-budget-raise: .claude/skills/deep-code-review/references/tool-hub.md 59805→61157 hub rows for skillspector and mcp-scanner with verification evidence
