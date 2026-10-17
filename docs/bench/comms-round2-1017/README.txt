communication-structure round 2 against humanizer, 2026-10-17. Cost: $0 (free PCSS models only; ledger.jsonl has every call's token usage, including refused calls).

BLUF
- REVERT. The candidate edit scored 0.438, 95% CI [0.312, 0.562], n=40 fresh held-out scenarios, primary judge DeepSeek-V4-Flash, both orders, strict agreement. The preregistered bar is a lower bound above 0.5, so it fails. No SKILL.md, template or eval edit is committed; only this bench ships.
- The corroborating judge GLM-5.2 is worse for the edit: 0.218 [0.115, 0.333] on the 39 of 40 scenarios it finished.
- The unedited skill scored 0.312 [0.200, 0.425] on the same set, so the edit's own share is about +0.125 and the intervals overlap. Neither version beats humanizer on this host.

Root cause (from the 13 clear losses in ../loss-fix-1017 and the tune-split outputs)
The rival's answer is a send-ready email (subject line, greeting, connected prose, sign-off) with a stated recommendation and each option's cost in a sentence. Ours was a headed memo with bullet fragments and status emoji that listed options and asked the reader to choose. Answer length was not the cause (tune split: 4,513 words for the edited skill vs 4,618 for the rival).

Edit tested (arm PERUN, prompts/PERUN.txt)
Email form for a status update or reply sent to a named person (PR bodies, tracker comments, executive summaries and docs excluded); a decision message states a lean before the ask, the author's at its stated strength or else one derived from the source's own facts and flagged to the author as derived. It relaxed one old rule (no recommendation the author did not give).

Tune split (the 20 scenarios of round 1, primary judge only, scenarios_tune.json; prompts V1..V4)
unedited 0.150 [0.050, 0.275]; V1 email form as an inline clause 0.325 [0.175, 0.475]; V2 email form as its own rule with a worked example 0.250 [0.100, 0.400]; V3 plus PR and executive-summary exclusion and a derived lean 0.300 [0.150, 0.475] (2 of 20 answers stated a lean); V4 one coherent lean policy 0.300 [0.150, 0.475] (8 of 20 stated a lean). V4 was frozen. All four are within noise of each other; the largest tune gain was the email form.

Held-out (results_held.json, PREREGISTERED.md and SHA256-frozen.txt written before any held-out call)
- PERUN vs RIVAL, DeepSeek-V4-Flash, n=40: 0.438 [0.312, 0.562]; 10 clear wins, 15 clear losses, 15 splits. FAIL.
- BASE vs RIVAL, DeepSeek-V4-Flash, n=40: 0.312 [0.200, 0.425]; 6 clear wins, 21 clear losses, 13 splits.
- PERUN vs RIVAL, GLM-5.2, n=39 of 40: 0.218 [0.115, 0.333]; 4 clear wins, 26 clear losses, 9 splits. Descriptive only (partial: slow reasoning model, one verdict missing after read timeouts on all retries; 79 of 80 verdicts).
- Slot-1 rate (share of verdicts that picked Response 1): DeepSeek-V4-Flash 0.675 over 160 verdicts (no ties, so the same with and without ties; PERUN pairs 0.688, BASE pairs 0.662); GLM-5.2 0.557 over 79 verdicts (no ties). DeepSeek clearly favors slot 1; both-order strict scoring cancels this because each arm sits in each slot once per scenario. The generator (Qwen3.5-397B-A17B) never judged.

Post hoc, descriptive only (not part of the keep rule; chosen after seeing the results)
By type, DeepSeek, PERUN vs BASE win rate: 16 status notes 0.406 vs 0.094; 12 PR bodies 0.458 vs 0.458; 12 executive summaries 0.458 vs 0.458. The email form and the derived lean helped where the request is a message to a person; the PR and executive-summary answers did not change. A follow-up round could target those two types, but it would need its own fresh held-out set.

Caveats
Non-Claude generator and judges; both skills were written against Claude, so this result does not transfer to Claude in either direction. n=40, one scenario set, sampling not seeded, no lint-and-rewrite loop. Tuning and the keep decision used the same primary judge family. ledger.jsonl also holds refused calls (HTTP 403 from the sandbox proxy, no cost) from one accidental offline re-score; they produced no verdicts. The GLM-5.2 run was left to finish; its last verdicts arrived after the first commit of this directory, which is why the numbers here differ slightly from that commit message (0.194 on 36 scenarios).
