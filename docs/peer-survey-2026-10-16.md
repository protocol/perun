# Peer survey and field measurements, 2026-10-16

The roadmap in [roadmap.md](roadmap.md) cites this page as the source for peer-reported pain points. It is a relay, not a measurement made in this repository: the operator who ran the survey supplied the rows and numbers below. They are not independently verified and carry no per-item counts of how many peers named each row. A roadmap input that cites a row here is "sourced" only in the sense that a peer reported it.

## Survey rows

### P1
Hook reruns take 2 to 15 minutes.

### P2
Gates run 3 times per tree.

### P3
The sandbox blocks gh, Chromium, Postgres and tsx IPC.

### P4
Lanes end their turn while background tests still run.

### P5
Flaky tests drop PRs from trains.

### P6
A pr_state one-shot command is wanted.

### P7
A lane-handback automator is wanted.

### P8
A sandbox preflight is wanted.

### P9
Reply-cap rewrites.

### P10
Re-deriving state after compaction.

## Field measurements relayed on 2026-10-16

### F1
Delivery dedup: a hook cycle of 47 minutes fell to 30 seconds once repeated gate runs on one tree were deduplicated (3 runs per tree to 1).

### F2
Autonomy: about 5 sandbox-blocked retries per session.

### F3
Zero-chat lanes: no measurement was supplied. Lanes that keep chat to one status line and put deliverables in files were reported as wanted.
