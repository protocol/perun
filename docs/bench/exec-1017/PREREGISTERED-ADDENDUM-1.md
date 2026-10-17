# Addendum 1 (2026-10-17, before any keep/revert decision and before any held-out reasons were read)

Reason: the first baseline pass called `GLM-5.2` in its default thinking mode for the tiebreak. In 29 of 60 calls it spent the full 6000-token budget thinking and returned empty content, or timed out (`IncompleteRead`, `HTTPError`), at 50 to 540 seconds per call, so one scenario could block a run for up to about 50 minutes.

Change (one line of `bench.py`): the tiebreak call now passes `chat_template_kwargs: {"enable_thinking": false}` with `max_tokens` 600 (the same switch used for the generator; the judge call asks for JSON only). Nothing else changed: prompts, scenarios, arms, order randomization, scoring and the keep rule are as preregistered. DeepSeek calls are unchanged.

Handling: every judge record produced before this change (all of `judge/agentic-ceo/PERUN_v0/`, which used thinking-mode GLM) is deleted and re-judged with the amended driver on the unchanged saved generations. The agentic-ceo tune-set reasons were read once before this change; no held-out reasons were read. New hash of `bench.py` is in `SHA256-after-addendum-1.txt`.
