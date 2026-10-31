# Perun doctor and uninstall

Installed scripts and hooks can sit in a repo and never run: an operating layer that needed an extra flag, a stale global copy, forked scripts that drifted. Nothing used to report it. Now something does.

## Check an install

```bash
python3 scripts/perun_doctor.py [REPO]          # read-only table; exit 0 = clean, 1 = something to fix
python3 scripts/perun_doctor.py [REPO] --fix    # prints the plan, asks you to type yes (or pass --yes), replays flags, re-checks
```

Run from your deep-code-review checkout (pull it first: "latest" means this checkout's version). It checks:

| Check | Meaning |
|---|---|
| installed version | repo copy vs this checkout |
| global copy | `~/.claude/skills/deep-code-review` vs this checkout (never changed by `--fix`; run `./install.sh ~` yourself) |
| stale local skills | a repo-local `.claude/skills/<perun skill>/SKILL.md` whose `version:` is older than the global copy (`~/.claude/skills`). The local copy shadows the newer one, so the stale one silently wins. Plugin skills are namespaced (`plugin:skill`) and coexist with repo-local ones, so they are not compared. The WARN names both versions and paths; fix by removing or updating the repo-local copy. A missing copy, unparsable version (1-4 dot-separated numbers; `1.2` equals `1.2.0`), repo equal to home, or a symlinked skills dir shows INFO n/a |
| hook files exist | every `.py`/`.sh` a hook command names is present |
| hooks wired | each operating-layer script (`pipe_mask_guard`, `subagent_start_inject`, `handback_cap`) is called by a hook, else "installed but never runs" |
| manual-only scripts | informational: scripts no hook, workflow, loop or other script calls |
| drifted copies | skill files, or loose copies of Perun scripts elsewhere in the repo, whose sha256 differs from the checkout |
| janitor/scheduler | informational (INFO, never fails the exit code): a janitor or scheduler file exists, so something runs Perun without you. Install does not ship one |
| policy file | informational (INFO): a `perun-policy` file exists. Optional; defaults apply without it |
| commit identity | WARN only, shown only when it fires: this checkout's effective `git config user.email` (global config included) is not a noreply form (`*@users.noreply.github.com`, `noreply@*`) or listed in the gitignored `.identity-allow.local.txt`, yet every author of the default branch's last 10 commits is. Commits made here would publish that address (the pre-push hook refuses them too). Fix: `git config user.email <id>+<username>@users.noreply.github.com`. The address is masked in the output |
| review scanners | the last `review_checks.sh` run (recorded in the git common dir): WARN when scanners it wired did not run, or ran without their offline cache, and `provision_tools.sh --print` fixes it (it prints one install-and-warm-caches line to paste yourself outside the sandbox; an osv-scanner fix names this repo as DIR so its DB re-downloads). INFO with no record, no provisioning fix, or a scanner that ran with a partial scope (trivy secret-only, semgrep with errors); OK when everything wired ran in full |

After the table the doctor (and `install.sh`, before its last three lines) prints one advisory section, **To run autonomously, add:**, from `agentic-delivery/scripts/sandbox_preflight.py`. It is read-only and never changes the exit code or writes a settings file. It reads the repo's `package.json` scripts, Makefile, git hooks, `scripts/` and python tool config plus the settings that already apply (`.claude/settings.json`, `.claude/settings.local.json`, `~/.claude/settings.json`) and prints only what is missing. The safety boundary is the OS sandbox, so the main output is sandbox config: `sandbox.enabled`, `sandbox.excludedCommands` for commands the sandbox breaks (tsx IPC, headless browsers, database clients, `gh` TLS on macOS, docker, git over SSH on macOS, followed through scripts to the command the agent types), the allowed domains, `allowLocalBinding` and `allowWrite` those flows need. It adds `permissions.deny` for destructive git, `rm -rf` and `sudo`, and `permissions.ask` for publish, deploy and release commands. `permissions.allow` patterns for the repo's test, lint and build commands (by name) and `git push <remote> HEAD` are printed with a disclosure that they run repo-controlled code and are safe only with the sandbox enabled; if the sandbox is not enabled in the settings that apply, no allow rule is printed and it tells you to enable the sandbox first. It also lists what stays blocked or asks you on purpose (release commands, force-push, writes outside the repo, other repos, `gh pr create`) and the per-host mechanism the docs confirm (Claude Code settings and `/permissions`, Codex `approval_policy` and `sandbox_mode`). Every allow rule is checked against `destructive_guard.py`. The scan is regex-based, so treat each line as a lead; sources and dates are in `docs/standards-index.md` (2026-10-16). Run it alone with `python3 .claude/skills/agentic-delivery/scripts/sandbox_preflight.py [REPO]`.

`--fix` prints the plan and what the default-on operating layer would add to your settings, then needs a typed `yes` on a terminal (or `--yes`, which prints a warning). It exits non-zero if the reinstall fails. It only re-runs `install.sh` with the recorded flags (existing skill copies move to `<host>/skill-backups/` first; a backup identical to the fresh copy, or to the unedited copy the previous install wrote, is not kept, so unchanged re-runs and version bumps add nothing; install never deletes any other backup). It does not delete loose forks, touch the global copy, or invent a janitor or policy.

## Default-on operating layer

`./install.sh --with-delivery` (and `--full`) now applies the operating layer to `.claude/settings.local.json` by default (needs `jq`; without it the snippet is written as `.new` to merge by hand). Opt out with `--no-operating-layer`. The install prints what it changed and how to undo it.

## Uninstall

```bash
python3 scripts/perun_uninstall.py [REPO]            # dry run: prints the plan, changes nothing
python3 scripts/perun_uninstall.py [REPO] --apply    # does it
```

It trusts only `.claude/.perun-install.json`, written by `install.sh` (no marker: nothing is removed; re-run `install.sh` once). The rule is that nothing is deleted unless it is provably an unmodified, shipped Perun copy inside the repo. Settings are parsed first; invalid JSON aborts with no change, and the file is replaced by temp file plus rename. It removes only the hook entries, env values and sandbox/permissions values the marker recorded, and the `model` key only if Perun set it (the settings file itself goes if install created it and nothing else is in it). A skill file is removed only if its sha256 equals a hash install itself shipped; files you added or edited stay and are listed, and your pre-install copy is moved back into place (not copied, not deleted) when the whole dir was removed. A `skill-backups/` dir is removed only when every file in it is a shipped copy; any backup with a file that is not shipped, was edited, or sits behind a symlink is kept and listed as `kept: user content`. It also removes `house-defaults.md`, `settings.local.json.bak.<timestamp>` files and `AGENTS.md` blocks that install wrote (and `AGENTS.md` itself if install created it), then any directory that is now empty. A marker key with `..`, an absolute path or a malformed skills/backup dir aborts the run with no change; a path with a symlink in any component is skipped, never walked. Every delete is one file at a time, only for paths in the marker; nothing uses `rm -rf`.

## Releases and tags

`scripts/land-release.sh` stamps the release and never tags. After the release commit is on origin/main, run `scripts/land-release.sh tag` from a checkout at that commit: it creates and pushes the annotated `vX.Y.Z`, skips a tag that already exists locally, and refuses if origin/main is not at your version.
