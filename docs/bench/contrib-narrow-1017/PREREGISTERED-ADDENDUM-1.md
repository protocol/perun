# Addendum 1 (before any scenario was drawn or any arm was generated)

The first `bench.py write tune` call failed: the writer returned "NN text" paragraphs, not a JSON array, and the driver had no fallback for that. No scenario was written and no arm was generated. The driver now parses that shape the way `docs/bench/contrib-safety-1017/bench.py` does. New hash of `bench.py` in `SHA256-amend.txt`; the decision rule, seeds and v0 are unchanged.
