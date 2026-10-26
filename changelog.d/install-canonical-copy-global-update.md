### Changed
- `install.sh` writes one canonical skill copy in `.claude/skills` and symlinks the other hosts (`.cursor`, `.agents`, `.codex` and the extra roots) to it, so vendored copies cannot drift. If `ln -s` fails, or `DCR_COPY_HOSTS=1` is set, it falls back to real copies. A re-run leaves correct links alone (no backup churn), and `perun_uninstall.py` removes the links.

### Fixed
- `perun_doctor.py` prints one exact copy-paste `update-installed.sh` command when the user-global `~/.claude` install is stale (auto-update and `--fix` cannot reach it, and a classifier-denied updater is never bypassed). It now skips the git probe for a global or non-git target, and flags a real host copy that differs from the `.claude` copy by hash. The updater logs `pr skip: target is not a git repo (global install)` instead of `fetch origin failed` for such a target.
