### Added
- `scripts/rival_eval.py` records real per-arm usage (`prompt_tokens`, `completion_tokens`, `spend_usd`) from the PCSS response or `claude -p` JSON into `results.json` `cost_per_arm`, with a per-output sidecar so resumed runs keep it; arms without reported usage stay unmeasured.
- `scripts/bench_verdict.py --cost results.json` prints per-arm cost per item and the Perun/rival ratio and exits 1 unless Perun cost <= rival cost.
