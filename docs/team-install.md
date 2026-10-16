# Team-wide install through a Claude Code plugin marketplace

This repository is its own marketplace (`.claude-plugin/marketplace.json`, name `perun`, one plugin,
`perun`, source `.`). Schema and behavior below follow the Claude Code plugin docs, verified
2026-10-07 (URLs in [`standards-index.md`](standards-index.md)).

```bash
claude plugin marketplace add protocol/perun   # or /plugin marketplace add ... in a session
claude plugin install perun@perun
```

Run it as `/perun:review [DIFF <base> | FULL | FILE <paths>]`, `/perun:deliver <change>`
or `/perun:cost-retro`; every skill is also `/perun:<skill>`.

**Org admins** push it to every machine with managed settings (server-managed, MDM, or a
`managed-settings.json` file):

```json
{
  "extraKnownMarketplaces": {
    "perun": { "source": { "source": "github", "repo": "protocol/perun" }, "autoUpdate": true }
  },
  "enabledPlugins": { "perun@perun": true }
}
```

**Updates.** Each release bumps `plugin.json`'s `version` (the only version field; the marketplace entry
carries none), and a user receives a new copy only when that version changes. Background auto-update is off
unless the user enables it or the managed entry sets `"autoUpdate": true` as above. Without it, run
`/plugin marketplace update perun` or `claude plugin update perun@perun`.

**Pinning.** Tracking `main` is the default. To hold a team on a release, add the marketplace with a ref:
`.../perun#<tag-or-branch>` (or `"ref"` in the managed `source`) and set `"autoUpdate": false`.
Release tags can lag the version; check `git ls-remote --tags` for what exists before pinning.

**Spend and cost.** Name API keys `<tracker-project-id>-<handle>` and total an export per project
(`agentic-delivery/scripts/spend_report.py`); see [`token-cost-tips.md`](token-cost-tips.md).

**Host safety.** Which agent hosts have an OS sandbox and what to set: [`host-safety.md`](host-safety.md).
