# Registers the pipeline_hub.py tests (per-workflow and per-job percentiles, flakes, duplicate checks, OSS adapter and fallback, CLI) and the gh_rest proxy-header fix. Offline.
python3 scripts/test_pipeline_hub.py
python3 scripts/test_gh_rest_proxy_headers.py
