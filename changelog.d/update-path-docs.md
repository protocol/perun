### Changed
- `perun_doctor.py`: the "stale local skills" row now follows Claude Code's precedence (personal over project skill). WARN when the global copy is older than the repo-local one, with the command that updates the home-directory install; an older repo-local copy is INFO. Only `.claude/skills` is read. The "global copy" row says a global install auto-updates after the cooldown when `~/.claude/.perun-install.json` exists and stays manual otherwise.
- `docs/getting-started.md` section 4: documents the `auto_update_delay_h` cooldown (default 72, 0 = at once), an "Update now" recipe (home directory first, then the project; plugins use `/reload-plugins`) and that a sandbox write-protecting `.claude` also needs the `!` prefix. `docs/team-install.md` and a new README "Update Perun" section link to it.

### Added
- `perun_doctor.py`: "newest release" row per install with a `.perun-install.json` marker. One tag listing (`ls-remote --tags --refs`, 10 s timeout, no token) compares the install with the newest tag, shows the updater's last log line and prints the take-it-now command. Offline, timeout and no marker are INFO, never WARN or FAIL; `DCR_NO_PROBE` skips it.
