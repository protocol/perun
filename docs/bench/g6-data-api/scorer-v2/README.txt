Live scorer (v2.3) for set2 and later sets: run_and_score.py and agentic_arm.py, with their self-tests.
It is the top-level scorer relocated one level down with only path roots changed (bench dir = parent of this folder); see the "relocated" event in ../ledger.jsonl.
The set4+ pre-registration names this folder in its freeze list, so edits here after that point are amendments that must be ledgered.

Runbook (v2.4, fail-fast): launch agentic_arm.py as ONE harness-tracked command with api.anthropic.com (and any other model host) in that command's network allowlist.
Never nohup, disown or `&` detach it: sandbox network is granted per command, and a detached launch loses it (set4: 5 of 6 fixtures failed with ERR_PROXY_TUNNEL at $0).
The arm now probes api.anthropic.com once before any fixture and stops after the first infrastructure fault (proxy, tunnel, connection, 5xx or overloaded error, or no skill loaded at $0); errors.json carries a stop starting "infrastructure fault".
A stop means: fix the launch, then re-run per that set's PREREG. A plain model error (for example an empty report) still just records an error and continues.
