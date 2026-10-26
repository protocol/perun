### Added
- `install.sh --dry-run` installs into a throwaway empty directory and lists the files it would write, without touching the target. Every install now ends with a summary of the files written, split into vendored (skills, gate templates) and generated (AGENTS.md, commands, settings, the uninstall record).
- A bash 3.2 portability gate (`scripts/test-bash3-portability.sh`, with a planted-RED fixture) fails on bash-4-only constructs (`declare -A`, `mapfile`, `readarray`, `${var,,}`, `${var^^}`, `&>>`, `|&`, `coproc`) in shipped shell scripts. Lines may opt out with a `bash4-ok` comment. The scan found no real hits; two quoted-text false positives carry the marker.

### Changed
- install.sh adds the settings backups (`.claude/settings.local.json.bak.*`), the uninstall record (`.claude/.perun-install.json`) and `.perun/` to the target's `.git/info/exclude` (idempotent, never a tracked `.gitignore`), so they no longer show up as untracked files.
