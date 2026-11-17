#!/usr/bin/env bash
# Test: tagging happens only after the release commit is on origin/main (`land-release.sh tag`), never at land time;
# an existing local tag is skipped, not fatal. Temp bare remote, copy of this repo.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-tag.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null RELEASE_DATE=2026-01-01
export GIT_AUTHOR_NAME=T GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=T GIT_COMMITTER_EMAIL=t@example.com
fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; else echo "FAIL  $2"; fail=1; fi; }
R="$WORK/repo"; mkdir "$R"
g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git init -q --bare -b main "$WORK/origin.git"
rsync -a --exclude=.git --exclude=.claude/worktrees --exclude=changelog.d "$ROOT/" "$R/"
git -C "$R" init -q -b main; g remote add origin "$WORK/origin.git"
g add -A; g commit -q -m base; g push -q origin main
V0=$(cat "$R/.claude/skills/deep-code-review/VERSION"); exp="${V0%%.*}.$(( $(echo "$V0" | cut -d. -f2) + 1)).0"
g checkout -q -b lane main
mkdir "$R/changelog.d"; printf '### Added\n- tag test.\n' >"$R/changelog.d/t.md"
g add -A; g commit -q -m lane
(cd "$R" && bash scripts/land-release.sh) >/dev/null; ok $? "land succeeds"
[ -z "$(git -C "$R" tag -l "v$exp")" ] && [ -z "$(git -C "$WORK/origin.git" tag -l "v$exp")" ]; ok $? "land creates no tag"
(cd "$R" && bash scripts/land-release.sh tag) >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "tag before the release is on origin/main is refused"
[ -z "$(git -C "$WORK/origin.git" tag -l)" ] || [ -z "$(git -C "$WORK/origin.git" tag -l "v$exp")" ]; ok $? "nothing pushed by the refused tag"
g push -q origin HEAD:main
(cd "$R" && bash scripts/land-release.sh tag) >/dev/null; ok $? "tag after merge succeeds"
[ "$(git -C "$R" cat-file -t "v$exp")" = tag ]; ok $? "local tag v$exp is annotated"
[ "$(git -C "$WORK/origin.git" rev-parse "v$exp^{commit}")" = "$(g rev-parse HEAD)" ]; ok $? "remote has v$exp at the release commit"
out=$(cd "$R" && bash scripts/land-release.sh tag 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q "already exists locally; skipping" <<<"$out"; ok $? "existing local tag is skipped with a message, exit 0"
g tag -d "v$exp" >/dev/null; git -C "$WORK/origin.git" tag -d "v$exp" >/dev/null
g tag "v$exp" "$(g rev-parse HEAD~1)"   # stale local tag on the wrong commit
(cd "$R" && bash scripts/land-release.sh tag) >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "local tag on a different commit is refused"

# --- signed-tags policy (release-signers file present) ---
g tag -d "v$exp" >/dev/null
K="$WORK/keys"; mkdir "$K"
ssh-keygen -q -t ed25519 -N '' -f "$K/a" -C a@example.com; ssh-keygen -q -t ed25519 -N '' -f "$K/b" -C b@example.com
SF="$R/.claude/skills/agentic-delivery/release-signers"
printf 'a@example.com %s\n' "$(cut -d' ' -f1,2 "$K/a.pub")" >"$SF"
g add -A; g commit -q -m signers; g push -q origin HEAD:main   # policy is read from origin/main, not the tree
sign() { GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=gpg.format GIT_CONFIG_VALUE_0=ssh GIT_CONFIG_KEY_1=user.signingkey GIT_CONFIG_VALUE_1="$1" bash "$R/scripts/land-release.sh" tag; }
clean() { g tag -d "v$exp" >/dev/null 2>&1; git -C "$WORK/origin.git" tag -d "v$exp" >/dev/null 2>&1; true; }
(cd "$R" && sign "$K/a") >/dev/null 2>&1; ok $? "signers file: tag signed by an allowed key is pushed"
[ -n "$(git -C "$WORK/origin.git" tag -l "v$exp")" ]; ok $? "signed tag reached the remote"
clean
(cd "$R" && sign "$K/b") >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "signers file: tag signed by another key is refused"
[ -z "$(git -C "$WORK/origin.git" tag -l "v$exp")" ]; ok $? "other-key tag not pushed"
clean
(cd "$R" && bash scripts/land-release.sh tag) >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "signers file: no signing key configured is refused"
[ -z "$(git -C "$WORK/origin.git" tag -l "v$exp")" ]; ok $? "unsigned tag not pushed"
clean
rel=$(g log -1 --format=%H origin/main -S"$exp" -- .claude/skills/deep-code-review/VERSION)
g tag -a "v$exp" -m x "$rel"   # on the release commit itself, so only the signature check can refuse it
(cd "$R" && sign "$K/a") >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "signers file: pre-existing unsigned local tag is refused"
[ -z "$(git -C "$WORK/origin.git" tag -l "v$exp")" ]; ok $? "pre-existing unsigned tag not pushed"
clean
# unsigned remote tag on the release commit (same sha, different tag object): refused when signers exist
g tag -a "v$exp" -m x "$rel"; g push -q origin "refs/tags/v$exp"; g tag -d "v$exp" >/dev/null
(cd "$R" && sign "$K/a") >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "signers file: unsigned remote tag on the same commit is refused"
clean; rm "$SF"   # deleted from the working tree only: origin/main still has it
(cd "$R" && bash scripts/land-release.sh tag) >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "signers deleted in tree but on origin/main: unsigned tag refused"
[ -z "$(git -C "$WORK/origin.git" tag -l "v$exp")" ]; ok $? "tree-deleted signers: tag not pushed"
clean
printf 'b@example.com %s\n' "$(cut -d' ' -f1,2 "$K/b.pub")" >"$SF"   # tree-only edit allowing key b
(cd "$R" && sign "$K/b") >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "signers edited in tree only: other-key tag refused"
clean; rm "$SF"
g rm -q "$SF" 2>/dev/null || g rm -q --cached .claude/skills/agentic-delivery/release-signers; g commit -q -m "drop signers"; g push -q origin HEAD:main
(cd "$R" && bash scripts/land-release.sh tag) >/dev/null 2>&1; ok $? "no signers file on origin/main: unsigned annotated tag still pushed"
exit $fail
