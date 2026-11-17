### Security
- Auto-update now waits a cooldown (policy key auto_update_delay_h, default 72 hours, 0 applies at once) after it first sees a release tag, and it re-checks the tag still points at the commit it saw. A malformed policy value falls back to 72.
- Auto-update refuses a tag that is not annotated or whose own name header differs from the tag name, which blocks re-pushing an old release under a newer name. If the installed copy ships a release-signers file, the tag must also pass git verify-tag against it.
- An empty or comment-only SHA256SUMS now fails the update, and SECURITY.md records the status as mitigated by the cooldown, not closed until release tags are signed.
- The dependency scope check now counts a production pnpm git+ssh dependency whose version string contains "@" as production instead of leaving it unknown.
