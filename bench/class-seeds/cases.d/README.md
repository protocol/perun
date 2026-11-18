# Class-seed cases (drop-in)

Add `bench/class-seeds/cases.d/<group>.json` (a JSON list) and `scripts/test_class_seeds.py` runs it next to the
in-file cases. No Python edit needed.

```json
{"class": "CWE-79", "seed": "cwe79.js", "tool": "semgrep", "rule": "perun.js.xss", "expect": [true, true], "why": ""}
```

- `seed`: a file or a directory under `bench/class-seeds/{vuln,clean,mutant}/` (same name in each).
- `tool`: `semgrep` (the whole `templates/semgrep-taint/` dir), `output_safety_check`, `cppcheck`, or
  `hub:<name>`. A hub seed is copied to the root of a fresh temp git repo and `review_checks.sh --base HEAD~1` (a seed with its own `.git`, i.e. a builder repo, runs `--full`)
  runs there (`REVIEW_SEMGREP_REGISTRY=0 CI=true`, temp HOME); a hit is a row from tool `<name>`.
- `rule`: substring the hit's rule or check id must contain (`""` = any rule of that tool).
- `expect`: `[vuln_hit, mutant_hit]`. The clean twin must be silent. A false entry needs a concrete `why`.
- `builder` (optional): name of `bench/class-seeds/builders/<name>.py`, exposing `build(dst, kind)` with `kind` in
  `vuln|clean|mutant`; it fills the empty dir `dst` at test time (secrets assembled from split parts, or a temp git
  history with `git` calls). With a builder, `seed` is unused. If `dst` has a `.git`, it is used as is.
- `flags` (optional): extra `review_checks.sh` flags for hub cases, e.g. `["--history"]`.
- `pin_only` (optional, `cppcheck` only): seed kinds, e.g. `["mutant"]`, that count only on the cppcheck version
  `.github/workflows/ci.yml` pins. On any other version the case prints `SKIP` naming both versions.
- A tool that did not run (not installed, or only `not-checked` rows) prints `SKIP` and counts as skipped, never ok.
