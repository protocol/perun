### Added
- review_checks.sh runs agent_workflow_injection.py on changed workflows: outsider-written issue, PR, comment or branch text reaching an AI-agent step, a pull-request head checked out beside an agent under pull_request_target, issue_comment or workflow_run, and agent steps with sandbox or approval off or an unrestricted Bash tool (tool `agent-injection`, leads for review).

size-budget-raise: .claude/skills/deep-code-review/references/appsec-supply.md 10495→11005 AI agent step injection leads paragraph
size-budget-raise: .claude/skills/INDEX.md 18224→18362 agent_workflow_injection row
size-budget-raise: .claude/skills/deep-code-review/INDEX-scripts.md 9383→9605 agent_workflow_injection row
size-budget-raise: .claude/skills/deep-code-review/references/review-config.md 6472→6888 resync the budget row to the size already on main
