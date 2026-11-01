### Added
- `review_checks.sh --full` now lists a password, one-time-code or reset-code check, or a sign-in, one-time-code or reset route, with no attempt-limit, lockout or auth-provider evidence in its file or package (`attempt_limit_map.py`, rule `missing-attempt-limit`). A row is a lead to confirm on a running instance with `dynamic_probe.py --rate-endpoint`, not proof that attempts are unlimited: a gateway, host or auth service may still limit them.
### Fixed
- `route_auth_map.py`, `header_config.py` and `tenant_scope_check.py` no longer read a `/*` or `//` that follows a backslash, as in the JavaScript regex literal `/\/*$/`, as the start of a comment. That misread could blank the rest of the file and hide the code after it from the scan (shared `mask()` in `tenant_scope_check.py`).
size-budget-raise: .claude/skills/deep-code-review/references/appsec-verify.md 7863→8075 one row pointing to the attempt-limit check
