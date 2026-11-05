### Added
- `cost_limit_map.py` and every consumer of the `route_auth_map.py` inventory (`--all`, attempt-limit, csrf-cookie) now see PHP handlers: Symfony `#[Route]` attributes and `@Route` annotations (with the class-level prefix) and Laravel `Route::get|post|put|patch|delete|any`. New cost kind `send` (email or SMS through a vendor API or library), a one-hop LLM-through-a-repo-helper rule, and `->chat(` style model-receiver calls. Tests in `scripts/test_cost_limit_recall.py`.

### Fixed
- `cost_limit_map.py`: a Go limiter that handlers attach only through `.With(limiter)` on another route's registration no longer counts as cover for unrelated routes (a `Use(limiter)` or module-level limiter still does), and limit evidence is no longer taken from a file of a different language family.
