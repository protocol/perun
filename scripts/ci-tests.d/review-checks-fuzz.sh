# review_checks.sh fuzz tool: opt-in (--fuzz / REVIEW_FUZZ=1) only; the test always runs stub-go cases and a real-go case on a seeded crashing fixture, which is skipped when go is missing; atheris, cargo-fuzz and jazzer are inventory rows only
bash scripts/test-review-checks-fuzz.sh
