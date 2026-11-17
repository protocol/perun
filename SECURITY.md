# Security policy

This repository ships markdown skills and local install scripts. There is no
networked service and no runtime sandbox.

## How to install a pinned copy (AST02 / AST07)

Do **not** `curl | bash` unsigned `HEAD`. Do **not** treat `npx skills add
owner/repo` without a tag as a pin — that follows whatever the default
branch is today.

Verified path:

```bash
git clone --branch vX.Y.Z --depth 1 \
  https://github.com/protocol/perun.git
cd perun
# optional: sha256sum -c SHA256SUMS
./install.sh /path/to/your/project
```

Replace `vX.Y.Z` with a published release tag (see GitHub Releases). The
AGENTS.md stamp records `Installed: **x.y.z** (@ sha)` after copy.

`SHA256SUMS` covers the three skill trees under `.claude/skills/`.
Regenerate with `bash scripts/write-checksums.sh`. Lane PRs do not commit it;
the land commit (the one that bumps `VERSION`) does, and CI checks the file
against the tree there. This is a content hash, **not** OpenSSF Model Signing —
do not claim a signed skill.

Optional marketplace path, still pinned:

```bash
npx skills add protocol/perun#vX.Y.Z --skill deep-code-review
```

Prefer `--copy` over a symlink that auto-updates. `npx skills update`
without a re-review is AST07. Default-on auto-update runs remote code from release tags: that high risk is MITIGATED by the
`auto_update_delay_h` cooldown (default 72h), not closed; it closes only once tags are signed and a `release-signers` file ships.
Signed releases: if `.claude/skills/agentic-delivery/release-signers` (ssh allowed_signers) exists, `land-release.sh` and `release.yml` refuse any release tag that does not verify against it; absent file = unchanged. The signers file is read from the base branch, not the tagged tree. The `release.yml` step only catches accidental unsigned tags: a tag-push workflow runs from the tagged commit, so a hostile tagger can edit it away. The real control is consumer-side `perun_auto_update` running `verify-tag` against the installed `release-signers`; also restrict `v*` tag creation to admins with a tag ruleset. The first `release-signers` file reaches an install through an update that could not yet be verified (trust on first use); installs made after it ships verify every later tag.

## Reporting a vulnerability

Open a private GitHub security advisory on this repository, or an issue
if the finding is already public. Do not file a proof-of-concept exploit
against systems you do not own.

## Honest gaps

- `install.sh` is local `cp -R`. It does not sign the payload.
- Required-review branch protection is off so a same-owner merge is not
  trapped. Status check `gates` is required.
- Secret-scanning validity checks and non-provider patterns are GitHub
  product settings; they may need GitHub Secret Protection. Do not claim
  they are on unless the live `security_and_analysis` payload says so.
