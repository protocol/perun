# Standards coverage: which class a hub scanner covers

Read this when a report, an owner or a buyer asks which OWASP Top 10:2025, OWASP API Security Top 10 2023, CWE Top 25 2025 or OWASP Top 10 for LLM Applications 2026 class `scripts/review_checks.sh` checks mechanically, and which ones rest on the reviewer alone.

IDs and names only. Per-class review depth: `security-appsec.md` (OWASP Top 10, CWE Top 25), `security-api.md` (API Top 10), `security-ai-agents.md` (LLM Top 10, the 2026 edition it walks). Tool routing: `tool-hub.md`. Sources and fetch dates: `docs/standards-index.md`.

Status:

- **wired**: the class is one weakness, and the hub's semgrep taint pack checks it with a source-to-sink rule for both JavaScript and Python, each rule with its own probe that fires under test. A probe is a `bench/class-seeds/` seed (run by `scripts/test_class_seeds.py`) or a test that carries `ruleid:` fixtures for the named rule. Wired still covers only the sources and sinks the pack's rules model, in the languages it has rules for.
- **partial**: a hub tool checks one slice of the class (named "via CWE-n" or in plain words): one language, one framework or config format, one heuristic script, or one weakness of a broad class. Also partial: a check with no seeded probe, one whose probe fires only under flags the hub does not pass, or one whose probe is verified only on a tool version CI does not pin.
- **none**: no hub check; review prose only.

A CWE entry MITRE rates Class (CWE-20, CWE-77, CWE-200, CWE-862, CWE-863) or Pillar (CWE-284) is broad: one narrow rule checks a slice of it, so its row is partial and names the slice. A multi-weakness OWASP class whose hub check covers one weakness is partial and names it "via CWE-n": a CWE the OWASP category page maps or references (OWASP Top 10, API rows), or the CWE the checked rule or its script labels (LLM rows); with no such CWE the row names the slice in plain words. `scripts/test-standards-coverage.sh` holds the wired IDs as an allowlist and fails when a row's status disagrees with it, an allowlisted ID has no row, a row ID repeats, a wired row lacks a `perun.js.*` and a `perun.py.*` semgrep rule or a probe per rule, a wired or partial row names a tool that `review_checks.sh` does not route (a `run_one` call on a non-comment line or a `verified` hub registry row), a wired row says "via CWE-", a semgrep rule is missing from `templates/semgrep-taint/`, any probe path does not exist, a test probe has no `ruleid:` fixture for the rule in the same position, a `bench/class-seeds/` probe has no `scripts/test_class_seeds.py` case (built-in or `cases.d`) for its rule with an expected vuln hit, a non-semgrep rule name is neither a literal in hub code nor named by a test or `cases.d` entry (cppcheck ids may instead be in `cppcheck --errorlist`), or a wired row has no probe.

## OWASP Top 10:2025

| ID | Name | Status | Hub tool, rule | Seeded probe |
|---|---|---|---|---|
| A01:2025 | Broken Access Control | partial | `ownership` `ownership-sibling` (via CWE-639) | `bench/class-seeds/vuln/api1-bola` |
| A02:2025 | Security Misconfiguration | partial | `semgrep` `perun.py.xxe-lxml` (via CWE-611) | `scripts/test_semgrep_py_guards.py` |
| A03:2025 | Software Supply Chain Failures | partial | `osv-scanner` any advisory (via CWE-1395) | `bench/class-seeds/vuln/a03-deps` |
| A04:2025 | Cryptographic Failures | partial | `bandit` `B324` (via CWE-327) | `bench/class-seeds/vuln/a04-crypto.py` |
| A05:2025 | Injection | partial | `semgrep` `perun.py.command-injection` (via CWE-78) | `bench/class-seeds/vuln/cwe78.py` |
| A06:2025 | Insecure Design | partial | `semgrep` `perun.js.upload-multer-no-filter` (via CWE-434 only, one of 39 mapped CWEs) | `bench/class-seeds/vuln/cwe434-upload.js` |
| A07:2025 | Authentication Failures | partial | `semgrep` `perun.js.guard-allows-missing-token` (via CWE-306) | `scripts/test_semgrep_audit_classes.py` |
| A08:2025 | Software or Data Integrity Failures | partial | `semgrep` `perun.py.deserialize` (via CWE-502) | `bench/class-seeds/vuln/cwe502.py` |
| A09:2025 | Security Logging and Alerting Failures | partial | `semgrep` `perun.js.log-sensitive` (via CWE-532) | `bench/class-seeds/vuln/a09-log-sensitive.js` |
| A10:2025 | Mishandling of Exceptional Conditions | partial | `semgrep` `perun.py.auth-fails-open` (via CWE-636) | `bench/class-seeds/vuln/a10-auth-fails-open.py` |

## OWASP API Security Top 10 2023

| ID | Name | Status | Hub tool, rule | Seeded probe |
|---|---|---|---|---|
| API1:2023 | Broken Object Level Authorization | partial | `ownership` `ownership-sibling` (one heuristic: a handler that loads a record by a client id when a sibling handler in the same file checks ownership) | `bench/class-seeds/vuln/api1-bola` |
| API2:2023 | Broken Authentication | partial | `attempt-limit` `missing-attempt-limit` (via CWE-307) | `scripts/test_attempt_limit_map.py` |
| API3:2023 | Broken Object Property Level Authorization | partial | `semgrep` `perun.js.mass-assignment` (via CWE-915) | `bench/class-seeds/vuln/api3-mass.js` |
| API4:2023 | Unrestricted Resource Consumption | partial | `cost-limit` `unbounded-body` (via CWE-770) | `bench/class-seeds/vuln/api4-body` |
| API5:2023 | Broken Function Level Authorization | partial | `privileged-route` `privileged-route` (one heuristic: a privileged route with authentication but no role check) | `bench/class-seeds/vuln/api5-priv` |
| API6:2023 | Unrestricted Access to Sensitive Business Flows | none | none | none |
| API7:2023 | Server Side Request Forgery | wired | `semgrep` `perun.js.ssrf` `perun.py.ssrf` | `scripts/test_semgrep_injection.py` `scripts/test_semgrep_audit_classes.py` |
| API8:2023 | Security Misconfiguration | partial | `semgrep` `perun.py.cors-reflected-origin` (via CWE-942) | `scripts/test_semgrep_defaults.py` |
| API9:2023 | Improper Inventory Management | partial | `semgrep` `perun.js.swagger-ui-ungated` (via CWE-1059) | `scripts/test_semgrep_inventory.py` |
| API10:2023 | Unsafe Consumption of APIs | partial | `semgrep` `perun.py.unsafe-api-consumption` (via CWE-20) | `scripts/test_semgrep_py_guards.py` |

## CWE Top 25 2025

The C and C++ partial rows: on 2026-11-24 `cppcheck` 2.22.0 fired `arrayIndexOutOfBounds` / `bufferAccessOutOfBounds` (its CWE-788) on a stack write, a heap write and a `strcpy` overflow, and `flawfinder` 2.0.20 lists CWE-120 rules (`--listrules`). Those were throwaway local runs, not seeds in this repo.

| ID | Name | Status | Hub tool, rule | Seeded probe |
|---|---|---|---|---|
| CWE-79 | Improper Neutralization of Input During Web Page Generation ('Cross-site Scripting') | wired | `semgrep` `perun.js.xss` `perun.py.xss` | `bench/class-seeds/vuln/cwe79.js` `scripts/test_semgrep_audit_classes.py` |
| CWE-89 | Improper Neutralization of Special Elements used in an SQL Command ('SQL Injection') | wired | `semgrep` `perun.js.sqli` `perun.py.sqli` | `scripts/test_semgrep_injection.py` `scripts/test_semgrep_audit_classes.py` |
| CWE-352 | Cross-Site Request Forgery (CSRF) | partial | `csrf-cookie` `missing-csrf-protection` (one heuristic: a state-changing handler in a cookie-session file with no CSRF protection found) | `bench/class-seeds/vuln/cwe352` |
| CWE-862 | Missing Authorization | partial | `route-auth` `missing-auth` (MITRE Class; one slice: a state-changing HTTP handler with no authentication evidence) | `scripts/test_route_auth_map.py` |
| CWE-787 | Out-of-bounds Write | partial | `cppcheck` `arrayIndexOutOfBounds` | none |
| CWE-22 | Improper Limitation of a Pathname to a Restricted Directory ('Path Traversal') | wired | `semgrep` `perun.js.path-traversal` `perun.py.path-traversal` | `bench/class-seeds/vuln/cwe22.js` `scripts/test_semgrep_py_pathtrav.py` |
| CWE-416 | Use After Free | partial | `cppcheck` `deallocuse` (verified only on cppcheck 2.22.0: the seed fires it there with the hub's default flags in a local run on 2026-11-24; CI pins cppcheck 2.13.0, unverified there, and `scripts/test_class_seeds.py` runs `--enable=warning`) | `bench/class-seeds/vuln/cwe416.c` |
| CWE-125 | Out-of-bounds Read | partial | `cppcheck` `arrayIndexOutOfBounds` (verified only on cppcheck 2.22.0: the seed fires it there with the hub's default flags in a local run on 2026-11-24; CI pins cppcheck 2.13.0, unverified there, and `scripts/test_class_seeds.py` runs `--enable=warning`) | `bench/class-seeds/vuln/cwe125.c` |
| CWE-78 | Improper Neutralization of Special Elements used in an OS Command ('OS Command Injection') | wired | `semgrep` `perun.py.command-injection` `perun.js.command-injection` | `bench/class-seeds/vuln/cwe78.py` `scripts/test_semgrep_injection.py` |
| CWE-94 | Improper Control of Generation of Code ('Code Injection') | wired | `semgrep` `perun.js.code-injection` `perun.py.code-injection` (zizmor template-injection also covers GitHub Actions expressions) | `scripts/test_semgrep_wired_cwe.py` `scripts/test_semgrep_wired_cwe.py` |
| CWE-120 | Buffer Copy without Checking Size of Input ('Classic Buffer Overflow') | partial | `flawfinder` CWE-120 rules (`strcpy`, `strcat`, ...) | none |
| CWE-434 | Unrestricted Upload of File with Dangerous Type | wired | `semgrep` `perun.js.unrestricted-upload` `perun.py.upload-save-unrestricted` | `scripts/test_semgrep_wired_cwe.py` `scripts/test_semgrep_upload.py` |
| CWE-476 | NULL Pointer Dereference | partial | `cppcheck` `nullPointer` (the hub runs default checks, which report only `uninitdata` and `uninitStructMember` on the seed; `scripts/test_class_seeds.py` runs `--enable=warning`, where the seed fires `nullPointerRedundantCheck`; adding `--enable=warning` to the hub is the upgrade path) | `bench/class-seeds/vuln/cwe476.c` |
| CWE-121 | Stack-based Buffer Overflow | partial | `cppcheck` `arrayIndexOutOfBounds` | none |
| CWE-502 | Deserialization of Untrusted Data | wired | `semgrep` `perun.js.deserialize-untrusted` `perun.py.deserialize` | `scripts/test_semgrep_wired_cwe.py` `bench/class-seeds/vuln/cwe502.py` |
| CWE-122 | Heap-based Buffer Overflow | partial | `cppcheck` `arrayIndexOutOfBounds` | none |
| CWE-863 | Incorrect Authorization | partial | `privileged-route` `privileged-route` (MITRE Class; one slice: a privileged route with authentication but no role check) | `bench/class-seeds/vuln/api5-priv` |
| CWE-20 | Improper Input Validation | partial | `semgrep` `perun.js.unvalidated-size-or-qty` (MITRE Class; one slice: a request value used as a size, count or price with no integer or range check) | `bench/class-seeds/vuln/cwe20.js` |
| CWE-284 | Improper Access Control | partial | `tenant-scope` `unscoped-tenant-access` (MITRE Pillar; no seed is labeled CWE-284; CWE-639, CWE-862 and CWE-863 under it are partial) | none |
| CWE-200 | Exposure of Sensitive Information to an Unauthorized Actor | partial | `semgrep` `perun.py.exception-in-response` (MITRE Class; one slice: exception text returned to the client) | `bench/class-seeds/vuln/cwe200.py` |
| CWE-306 | Missing Authentication for Critical Function | partial | `semgrep` `perun.js.guard-allows-missing-token` (one slice: an auth guard that lets a request with no token through) | `scripts/test_semgrep_audit_classes.py` |
| CWE-918 | Server-Side Request Forgery (SSRF) | wired | `semgrep` `perun.js.ssrf` `perun.py.ssrf` | `scripts/test_semgrep_injection.py` `scripts/test_semgrep_audit_classes.py` |
| CWE-77 | Improper Neutralization of Special Elements used in a Command ('Command Injection') | partial | `semgrep` `perun.js.command-injection` (MITRE Class; one slice: untrusted data reaching a shell command in JavaScript) | `bench/class-seeds/vuln/cwe77.js` |
| CWE-639 | Authorization Bypass Through User-Controlled Key | partial | `ownership` `ownership-sibling` (one heuristic: a handler that loads a record by a client id when a sibling handler in the same file checks ownership) | `bench/class-seeds/vuln/api1-bola` |
| CWE-770 | Allocation of Resources Without Limits or Throttling | partial | `cost-limit` `unbounded-body` (one heuristic: a handler that reads the whole request body with no size limit found) | `bench/class-seeds/vuln/api4-body` |

## OWASP Top 10 for LLM Applications 2026

| ID | Name | Status | Hub tool, rule | Seeded probe |
|---|---|---|---|---|
| LLM01:2026 | Prompt Injection | partial | `agent-injection` `agent-untrusted-input` (one slice: outsider-written issue, PR or comment text reaching an AI-agent step in a CI workflow) | `bench/class-seeds/vuln/llm01-agent-injection` |
| LLM02:2026 | Sensitive Information Disclosure | partial | `gitleaks` any rule (via CWE-798) | `bench/class-seeds/builders/llm02-secret.py` |
| LLM03:2026 | Excessive Agency | partial | `mcp-config` `agent-broad-allow` (one slice: a `permissions.allow` rule of `*`, `Bash` or `Bash(*)` in agent settings) | `bench/class-seeds/vuln/llm06-agent-allow` |
| LLM04:2026 | Supply Chain | partial | `semgrep` `perun.py.llm-trust-remote-code` (via CWE-94) | `bench/class-seeds/vuln/llm03-trust-remote-code.py` |
| LLM05:2026 | Data and Model Poisoning | partial | `semgrep` `perun.py.llm-torch-load-default` (via CWE-502) | `bench/class-seeds/vuln/llm04-poisoned-checkpoint.py` |
| LLM06:2026 | Unbounded Consumption | partial | `cost-limit` `missing-cost-limit` (via CWE-770) | `bench/class-seeds/vuln/llm10-cost` |
| LLM07:2026 | Misinformation | none | none in the hub; `product-output-safety`'s `output_safety_check.py` fires on seed `llm09.json` outside `review_checks.sh` | none |
| LLM08:2026 | Hidden Context Exposure | partial | `semgrep` `perun.llm.system-prompt-response-py` (via CWE-200) | `bench/class-seeds/vuln/llm07-prompt-leak.d` |
| LLM09:2026 | Vector and Embedding Weaknesses | partial | `semgrep` `perun.llm.vector-pinecone-py` (via CWE-639) | `bench/class-seeds/vuln/llm08-vector-tenant.d` |
| LLM10:2026 | Improper Output Handling | partial | `semgrep` `perun.js.llm-output-code-exec` (via CWE-95) | `bench/class-seeds/vuln/llm05.js` |
