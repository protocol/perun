# Deviations and caveats: review-cost V2 (2026-10-19)

Verdict: REVERT (keep rule A and B both false, see `results-heldout.json`). No SKILL.md was edited; a keep would have been a separate change.

1. Tune n differs by variant (V2a 19, V2b 18, V2c 18 of 21) because a case that errored twice on the free host is dropped per arm.
2. Held-out n is 21 of 22. `starlette-url-replace-empty-host` is dropped: for the V2 and V2s arms both judges returned no parseable verdict on repeated attempts. This follows the pre-registration (drop and report).
3. Tokens count input, cache creation, cache read and output, the same for every arm. Cache reads make the totals larger than prompt size alone.
4. The ledger total ($3.1769) covers 89 paid `claude -p` calls: 22 cases x 4 arms plus one quota probe. Judging used free PCSS models and is not in the ledger. Peak plan utilization read was 0.08.
5. V2s (the V2 skill copy loaded through the workspace with the PERUN request) is descriptive only and does not enter the keep rule.
6. The tune gain on the free host (F1 +0.220 against the toolkit, CI 0.053 to 0.392) did not transfer to Claude (+0.063, CI -0.099 to 0.249). Tune numbers were never evidence for the keep rule.
7. The branch base is the local `origin/main` ref at 84748edc5; `git fetch` failed with a proxy 403 in the sandbox, so the ref may lag the remote.
8. One run per case, judges are not Claude, and n=21 gives a wide interval; the result is a no-win read, not proof of equivalence.
