# Getting started with Perun

**You can try the review with no install by pasting one file into an AI chat.
To make every agent in a project use it, run `install.sh` from a pinned
release.** This page covers both, plus updating and removal. Perun is a suite:
deep code review, token and cost tools, gated agentic delivery, an idea critic and
product, growth, positioning, business-ops and output-safety specialists. What it
is and which skills exist: [the README](../README.md) and the [skill catalog](#skill-catalog) below.

## 1. Try it without installing

This works in any AI chat, with or without a coding agent.

1. Open [`SKILL.md`](../.claude/skills/deep-code-review/SKILL.md) and copy all
   of it.
2. Start a new chat. Paste the skill, then paste the file you want reviewed.
3. Ask: `Review this with scope FILE.`

A chat model sees only what you paste. It gets the method, severity scale, and
domain map, but not the detailed reference files, and it can't run your tests.
Treat this as a preview. For a full review, install Perun into a project where
an agent can read the files and run the build.

## 2. Install into a project

You need `git`, a terminal, and a coding agent that can open your project
(Claude Code, Cursor, Codex, Copilot, Gemini, Aider, Windsurf, OpenCode, Hermes,
Kiro, or similar).

```bash
git clone --depth 1 https://github.com/protocol/perun.git
cd perun && shasum -a 256 -c SHA256SUMS   # Linux: sha256sum -c SHA256SUMS
./install.sh --recommend /path/to/your/project       # optional: see a suggested pack, writes nothing
./install.sh /path/to/your/project                   # review only (the default)
```

Release tags lag the main branch, so this clones main; run `git rev-parse HEAD` and record the commit you reviewed. The checksum file ships in the same repository, so it catches a damaged copy, not a malicious one. Every
line of the checksum output should end in `OK`.

The default install copies `deep-code-review` into `.claude/skills/`,
`.cursor/skills/`, and `.agents/skills/` of your project and creates or updates
a marked block in `AGENTS.md` that records the installed version and commit. It
makes no network calls and needs no `sudo`.

### Choose where it lands

| Flag | Effect |
|---|---|
| *(none)* | `.claude/`, `.cursor/`, `.agents/` skill roots + `AGENTS.md` |
| `--with-codex` | also `.codex/skills/` |
| `--with-extra-hosts` | also the Gemini, OpenCode, Copilot, Windsurf, Hermes, Kiro, Cline, Roo Code, Factory Droid, Qwen Code, and Grok Build roots |
| `--minimal` | only `.claude/skills/` + `AGENTS.md` |
| `--claude-only` | only `.claude/skills/`, no `AGENTS.md` |

Add overlay skills with the flags in the
[skill catalog](#skill-catalog); `--full` adds delivery, critic, and
comms in one go. `./install.sh --help` is the authoritative list.

### Skill catalog

Only `deep-code-review` installs by default. The rest are opt-in flags on
`./install.sh`.

| Skill | Use it to... | Install flag |
|---|---|---|
| `deep-code-review` | review, harden or quality-gate a repo, PR or diff | **default** |
| `agentic-delivery` | build a feature under gated, multi-role delivery | `--with-delivery` |
| `idea-critic` | attack a plan before it reaches a decision maker | `--with-critic` |
| `communication-structure` | write a short, direct PR body, status update or report | `--with-comms` |
| `agentic-ceo` | route a multi-skill session and size the effort | `--with-ceo` |
| `product-discovery` | decide whether something is worth building | `--with-discovery` |
| `growth-analytics` | choose a main metric and read a funnel | `--with-growth` |
| `positioning` | shape a value proposition as a testable hypothesis | `--with-positioning` |
| `business-ops` | do pricing arithmetic; route legal or tax questions to a professional | `--with-business` |
| `product-output-safety` | govern harm from your product's own AI outputs | `--with-output-safety` |
| `contribution` | turn a lesson into a privacy-safe upstream pull request | `--with-contribution` |

If you already run another delivery framework, keep it and install review only.

## 3. Run your first review

Open the project in your agent and ask in plain words, or use the slash command
where your agent supports one:

```
run a deep code review DIFF origin/main    # just the changes on this branch
/deep-code-review FILE src/auth.ts         # named files
/deep-code-review FULL                     # the whole repository
```

Start with `DIFF` or `FILE`: they read less and cost less than `FULL`. The
agent first prints a short block stating the scope, the exact commit it pinned,
and the project type, then works through the phases. You get a short summary
in chat; the full findings table goes outside the repo unless you ask for it in
a `code-review/` folder. A worked example:
[`example-review-report.md`](example-review-report.md).

## 4. Update or remove

**Update:** with the operating layer (the default for `--with-delivery` and
`--full`), updates are automatic. A SessionStart/UserPromptSubmit hook checks the
newest `vX.Y.Z` tag on the remote you installed from, at most once every 6 hours,
in the background, and re-applies your recorded install flags from it with
`scripts/update-installed.sh`. Your existing settings win and backups are written.
It skips while a merge or train lock exists or you edited a Perun-managed file,
and appends one line per run to `~/.cache/perun/auto-update.log`. Open sessions
pick up the new skills and hooks without a restart; only a model change waits for
the next session. Turn it off with `"auto_update": "off"` in `.perun/policy.json`
or `install.sh --no-auto-update`. This runs the release's own install code, so
install only from a remote you trust. Before running it, the updater refuses a
local tag that moved, requires the tag's commit to be on the remote's `main`, and
checks the skill files against `SHA256SUMS` (the installer scripts are not in it). `SHA256SUMS`
comes from the same tag, so it proves skill-file integrity, not authenticity: trust rests
on the repository owner's tags and `main`.

**When auto-update cannot reach an install.** Two cases stay manual, and
`python3 scripts/perun_doctor.py` reports both. (1) A user-global install at
`~/.claude/skills` is not a project, so the hook never updates it: the doctor's
"global copy" row prints the one command to run (`DCR_NO_PULL=1 bash
<checkout>/scripts/update-installed.sh ~`). Global and non-git targets skip the git and repo
checks. (2) If the permission classifier denies the updater ("Code from External"),
Perun does not bypass it: run the same command yourself, with the `!` prefix inside Claude Code.

**One copy per install.** `install.sh` writes the real skill copy to `.claude/skills`
and symlinks `.cursor/skills` and `.agents/skills` (and other hosts) to it, so
copies cannot drift. If a symlink cannot be made, or you set `DCR_COPY_HOSTS=1`, it
writes real copies and the doctor's "drifted copies" row flags any that differ from the
`.claude` copy by hash.

Without the operating layer, pull or check out a newer release tag in your clone,
verify the checksums, and run `install.sh` again with the same flags. It copies
files; it never symlinks, so nothing changes until you re-run it.

To compare an installed copy's version with upstream `main`, run
`scripts/skill-drift-check.sh` from the clone. It reads
`~/.claude/skills/deep-code-review/VERSION` by default; for a project install,
set `DCR_INSTALLED_VERSION_FILE=/path/to/your/project/.claude/skills/deep-code-review/VERSION`.
It needs an authenticated `gh` CLI, exits `1` only when both versions were read
and differ, and exits `0` when they match or it can't check. `main` can be ahead
of the latest release tag, so a mismatch right after a pinned install is
expected.

**Remove:** run `python3 scripts/perun_uninstall.py <repo>` (dry run), then add `--apply`; it undoes
everything the install recorded. By hand instead: delete the skill folders it created under `.claude/skills/`,
`.cursor/skills/`, `.agents/skills/` (and any extra host roots), and delete the
`<!-- deep-code-review:begin -->` … `<!-- deep-code-review:end -->` block from
`AGENTS.md` (plus the `dcr-overlays` block if you installed overlays). If the
installer replaced an older copy, that copy is under `.<host>/skill-backups/` (a copy identical to the new one, or to the unedited copy the previous install wrote, is not kept; install never deletes any other backup).

## Next

- Running several agents in parallel: [`for-fleets.md`](for-fleets.md).
- Install safety and verification: [`SECURITY.md`](../SECURITY.md).
