# Addendum 3 (results; the decision rule is unchanged)

Held-out set `heldout60.json` (n = 60, sha256 in `SHA256-amend.txt`, hashed before any arm output); disjoint from every earlier contribution set (maximum 6-word-shingle overlap 0.032 against tune.json, heldout.json, heldout30.json and tune10.json). One run per arm, no re-runs.

Judge used: GLM-5.1 (slot-1 rate 0.444, inside 0.4 to 0.6), 60 of 60 scenarios scored, same judge for both arms.

| Measure (GLM-5.1) | Value [95% CI] |
|---|---|
| v0 (current SKILL.md) against the rival | 0.250 [0.158, 0.342] |
| Edit (narrowed SKILL.md) against the rival | 0.550 [0.458, 0.642]; strict 21 win / 24 tie-or-split / 15 loss |
| Paired difference, edit minus v0 | +0.300 [0.183, 0.417] |

Decision: SHIP (paired lower bound 0.183 is above 0). Superiority over the rival is not claimed: the edit's win-rate lower bound 0.458 is not above 0.5.

Sensitivity (reported, never the rule): GLM-5.2 (slot-1 0.512, healthy) v0 0.342 [0.242, 0.442], edit 0.600 [0.508, 0.692], paired +0.258 [0.125, 0.392]; gpt-oss_120b (slot-1 0.661, outside the gate) paired +0.325 [0.200, 0.450]. All three judges agree on the sign and on a paired lower bound above 0.

Caveats: Qwen3.5-397B-A17B generates every arm (the model the skill will not necessarily run on); judges are the PCSS models in `scripts/rival_eval.py`; the rival is one public skill (daymade github-contributor); the narrowed skill changes scope as well as wording, so the gain is for requests about contributing to another project and is not evidence about the skillset-lesson flow it no longer describes in prose.

Deviation, disclosed: after the held-out run the shipped `SKILL.md` differs from the tested `frozen/contribution.v1.md` in its description, its last section and two clauses. The repo's enumeration gate requires every eval id to be named in the Verification list, so that list now names all eleven ids (the tested text summarized them in prose). The clause is the existing lesson-ratchet test's required phrase: "otherwise file an issue" became "otherwise file an issue, never fold the prose". The description was reworded to name the trigger moments the trigger-coverage gate requires (`upstream improvement`, `generalizable lesson`, `lesson about the skillset`, `reusable`). The second clause names the local-imprint destination (`AGENTS.md`, `deep-code-review` Phase 6) that the existing `non-generalizable-imprint-locally` eval expects. Flow and answer shape are otherwise byte-identical.

Record format: judge verdict caches (one small file per verdict) were folded into one `judge-verdicts.json` per run to keep the repository's file count under the privacy gate's argument limit; every verdict is kept, and the win rates recompute from it.
