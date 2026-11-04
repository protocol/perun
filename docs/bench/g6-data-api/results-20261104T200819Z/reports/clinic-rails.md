# Security audit: clinic-rails

## Per-standard table
| Item | Status | Basis | Files | Negative |
|---|---|---|---|---|
| CSRF on cookie-session handlers | fail | tool:semgrep | app/controllers/account_controller.rb:2 | `skip_forgery_protection` |
| Route authn/authz map | not-checked | tool:route-auth | config/routes.rb | none |
| Attempt and cost limits | not-checked | tool:attempt-limit | app/controllers/public_controller.rb | none |
| PII exposure | not-checked | tool:pii-data | app/controllers/partners_controller.rb | none |

## NOT CHECKED
- Session cookie secret (secret_key_base): no credentials or env file in repo, deployed config unknown.
- Thread safety of Window and SESSIONS: runtime only.

## NOT RUN
- tenant-scope: SKIPPED: no *.prisma
- route-auth: SKIPPED: no HTTP handlers (Ruby not parsed; routes read by hand from config/routes.rb)
- header-config: SKIPPED: no supported web app
- attempt-limit: SKIPPED: no credential check or sign-in route
- cost-limit: SKIPPED: no HTTP handler
- csrf-cookie: SKIPPED: no HTTP handler or cookie
- pii-data: SKIPPED: no source file

## Static vs runtime
Needs a running system: deployed config, WAF, runtime authz, vault, infra outside the repo. The upstream vendor hosts, the PIN and DISPATCH_KEY env values and secret_key_base were not observable.

## Dependencies
trivy and gitleaks ran via review_checks.sh with no dependency or secret rows. No Gemfile.lock is committed, so rails ~> 7.2.1, httparty ~> 0.22 and puma ~> 6.4 resolve at install time; advisory and end-of-life status unverified.

## Attack paths
- Source-embedded admin token to data loss: store.rb:4 tok-admin as Bearer reaches canyon_approve and tundra_remove; cheapest cut is deleting the seeded SESSIONS.
- Nurse login to SSRF: tok-nurse (store.rb:3) or a PIN login reaches lagoon_fetch (partners_controller.rb:9), which fetches any URL such as cloud metadata; cut by allowlisting hosts.

## Findings
- [hardcoded-secret] app/models/store.rb:4 high: static admin bearer/cookie token "tok-admin" (and "tok-nurse" at line 3) is a permanent credential in source. evidence: app/controllers/application_controller.rb:11
- [ssrf] app/controllers/partners_controller.rb:9 high: lagoon_fetch GETs a caller-supplied params[:url] and relays the body, so any signed-in user can read internal or metadata URLs.
- [missing-authz] app/controllers/records_controller.rb:9 high: plover_purge deletes any row by id for any bearer holder, with no owner or admin check. evidence: config/routes.rb:47
- [missing-authz] app/controllers/records_controller.rb:15 high: sparrow_purge deletes any row by id for any bearer holder. evidence: config/routes.rb:48
- [object-level-authz] config/routes.rb:49 high: glacier_show returns any row regardless of owner (ROWS[params[:id]]).
- [object-level-authz] config/routes.rb:50 high: summit_show returns any row regardless of owner.
- [missing-authn] config/routes.rb:41 medium: heron_summary has no auth and lists every row id and label, including other owners.
- [missing-authn] config/routes.rb:42 medium: otter_summary has no auth and lists every row id and label.
- [missing-authn] config/routes.rb:15 low: poppy_join accepts unauthenticated requests with no limit.
- [rate-limit] app/controllers/public_controller.rb:12 high: bluff_pin checks the clinic PIN with no attempt limit, so the PIN can be brute-forced and yields a nurse token.
- [rate-limit] app/controllers/public_controller.rb:20 high: dune_pin is the same PIN check with no attempt limit.
- [tls-off] app/controllers/partners_controller.rb:5 high: delta_push sends the vendor API key with verify: false, allowing a man-in-the-middle.
- [secret-in-log] app/controllers/partners_controller.rb:21 high: savanna_ping logs VENDOR_KEY in clear text.
- [secret-in-url] app/controllers/partners_controller.rb:17 medium: prairie_lookup sends the vendor key as a query parameter, so it lands in URL logs.
- [secret-in-url] app/controllers/partners_controller.rb:26 medium: fjord_lookup sends the vendor key as a query parameter.
- [outbound-timeout] app/controllers/partners_controller.rb:13 medium: mesa_status calls the vendor with no timeout, so a slow upstream pins a Puma thread.
- [pii-in-log] app/controllers/partners_controller.rb:35 high: nettle_charge logs the card number and holder; filter_parameters does not cover an interpolated log string.
- [pii-in-log] app/controllers/public_controller.rb:28 high: maple_signup logs name, email and SSN. evidence: config/application.rb:9
- [pii-in-log] app/controllers/public_controller.rb:33 high: olive_signup logs name, email and SSN.
- [pii-data] app/controllers/partners_controller.rb:46 medium: sorrel_track posts the user's email and phone to the stats vendor.
- [pii-data] app/controllers/partners_controller.rb:39 medium: an SSN and date of birth are committed as seed data.
- [prompt-injection] app/controllers/partners_controller.rb:51 high: orchard_assist puts params[:note] into a system prompt that says the model may approve referrals.
- [prompt-injection] app/controllers/partners_controller.rb:55 high: ledger_lookup_tool builds tool-call JSON by string interpolation, so arg with a quote injects fields such as "tool".
- [rate-limit] app/controllers/partners_controller.rb:29 medium: cairn_export builds and renders 100,000 rows per call with no limiter, unlike reef_export.
- [rate-limit] app/controllers/partners_controller.rb:50 medium: orchard_assist calls the paid LLM with no limiter.
- [csrf] app/controllers/account_controller.rb:6 medium: shoal_email is a state-changing POST on cookie sid with skip_forgery_protection.
- [csrf] app/controllers/account_controller.rb:10 low: spire_close logs a user out cross-site because CSRF protection is skipped.
- [cookie-flags] app/controllers/account_controller.rb:15 high: clover_remember sets the sid session cookie without httponly, secure or same_site, and via a GET.
- [cookie-flags] app/controllers/account_controller.rb:20 medium: fennel_trust sets the session-token cookie without httponly.
- [other] app/models/store.rb:14 medium: open_session adds to SESSIONS with no expiry or cap, so repeated logins or cookie calls grow memory and tokens never expire.

## Route and entry inventory
Public (no auth): GET /healthz; GET /api/heron/summary, /api/otter/summary; POST /auth/moor-login (limited 8 per 600s), /auth/poppy-join, /auth/bluff-pin, /auth/dune-pin, /auth/maple-signup, /auth/olive-signup.
Bearer: GET /api/me, /api/badger, /api/valley/:id, /api/marten/recent, /api/glacier/:id, /api/summit/:id; DELETE /api/tundra/:id (admin); POST /api/canyon/:id/approve (admin), /api/plover/:id/purge, /api/sparrow/:id/purge; PUT /api/ridge/:id/label.
Bearer integrations: GET /api/ext/atoll/:id/image, geyser/:code/rates, tarn/:code/stock, reef/export (limited 5 per 60s), yarrow/sample; POST quince/rotate-key, tansy/track, parcel/assist, crate/lookup-tool.
Bearer partners: POST /api/ext/delta/push, nettle/charge, sorrel/track, orchard/assist, ledger/lookup-tool; GET lagoon/fetch, mesa/status, prairie/lookup, savanna/ping, fjord/lookup, cairn/export, rowan/sample.
Cookie sid (no CSRF): POST /web/ext/shoal/email, /web/ext/spire/close; GET /web/ext/clover/remember, /web/ext/fennel/trust.
Cookie session (CSRF on): POST /web/ext/arbor/phone, /web/ext/bramble/nickname; GET /web/ext/hazel/rotate, /web/ext/laurel/keep.
Other entry points: env DISPATCH_KEY and CLINIC_PIN; outbound calls to dispatch, img, stats and llm vendor hosts. No jobs, webhooks, CI workflows, uploads, MCP servers or CLI scripts found.