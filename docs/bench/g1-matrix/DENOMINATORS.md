# G1 denominators (committed before authoring)

Fetched 2026-11-05. Gate text: `docs/bench/security-ready-1103/PREREGISTERED.md`, section "G1 Standards matrix". The denominator of each list is every item below; no item is dropped. Verbatim ids and titles for all 318 items are in `items.json` (same directory); this file carries the counts, sources and hashes.

## Counts and sources

| List | Count | Source URL | sha256 of the fetched raw bytes |
|---|---|---|---|
| ASVS-5.0.0-L2 | 253 | https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv | `98c8fe911b9edb403af8ee05d3ce8201ecac2659e313b053890a62847cdcf680` |
| OWASP-Top10-2025 | 10 | https://top10.owasp.org/2025/ | `1203f554f0770ae735ca70bc9621ae6769d7d159eec74dede39a342bb17bc52d` |
| OWASP-API-Top10-2023 | 10 | https://api-security.owasp.org/editions/2023/en/0x11-t10/ | `ac00589e1bb28f4977b3c82dfb61713b7aac0cbd07b15bd40d8516ef86379524` |
| CWE-Top25-2025 | 25 | https://cwe.mitre.org/top25/archive/2025/2025_cwe_top25.html | `49a375800fa9519129a7beda6233dab499addfbe7952bfaedb9051654d2ab0db` |
| OWASP-LLM-Top10-2025 | 10 | https://genai.owasp.org/llm-top-10/ | `cd9c367d50b9fc3c21d3307fe8e7652000f3e212291db47cb6d181e632bf64fc` |
| OWASP-Agentic-Top10-2026 | 10 | https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/ | `3de48c24e4af6e05b38740c77d3a393bdf7f82edadb941151a615355d07e8b8c` |

Source notes:

- ASVS-5.0.0-L2: OWASP/ASVS tag v5.0.0 flat CSV; 345 rows in the file, count is rows with column `L` <= 2 (70 at L1 + 183 at L2; the 92 L3 rows are excluded).
- OWASP-Top10-2025: official site index page.
- OWASP-API-Top10-2023: official 2023 edition page.
- CWE-Top25-2025: MITRE 2025 archive page, ranks 1-25.
- OWASP-LLM-Top10-2025: official listing page.
- OWASP-Agentic-Top10-2026: official 2025-12-09 announcement (the resource landing page, sha256 d431f51e9c961b911d6500c845757796b6f8a9d18268d8073232596224c41cc9, links the PDF but does not list the titles; the PDF was NOT fetched, so the PDF wins on any conflict).

Unverified lists: none. Every count above comes from a source fetched this session. The Agentic list rests on the announcement, not the PDF (see note); if the PDF disagrees, this file is wrong and must be amended before authoring.

Total denominator: 318 items.

## OWASP-Top10-2025 (10)

| Id | Title |
|---|---|
| A01:2025 | Broken Access Control |
| A02:2025 | Security Misconfiguration |
| A03:2025 | Software Supply Chain Failures |
| A04:2025 | Cryptographic Failures |
| A05:2025 | Injection |
| A06:2025 | Insecure Design |
| A07:2025 | Authentication Failures |
| A08:2025 | Software or Data Integrity Failures |
| A09:2025 | Security Logging and Alerting Failures |
| A10:2025 | Mishandling of Exceptional Conditions |

## OWASP-API-Top10-2023 (10)

| Id | Title |
|---|---|
| API1:2023 | Broken Object Level Authorization |
| API2:2023 | Broken Authentication |
| API3:2023 | Broken Object Property Level Authorization |
| API4:2023 | Unrestricted Resource Consumption |
| API5:2023 | Broken Function Level Authorization |
| API6:2023 | Unrestricted Access to Sensitive Business Flows |
| API7:2023 | Server Side Request Forgery |
| API8:2023 | Security Misconfiguration |
| API9:2023 | Improper Inventory Management |
| API10:2023 | Unsafe Consumption of APIs |

## OWASP-LLM-Top10-2025 (10)

| Id | Title |
|---|---|
| LLM01:2025 | Prompt Injection |
| LLM02:2025 | Sensitive Information Disclosure |
| LLM03:2025 | Supply Chain |
| LLM04:2025 | Data and Model Poisoning |
| LLM05:2025 | Improper Output Handling |
| LLM06:2025 | Excessive Agency |
| LLM07:2025 | System Prompt Leakage |
| LLM08:2025 | Vector and Embedding Weaknesses |
| LLM09:2025 | Misinformation |
| LLM10:2025 | Unbounded Consumption |

## OWASP-Agentic-Top10-2026 (10)

| Id | Title |
|---|---|
| ASI01 | Agent Goal Hijack |
| ASI02 | Tool Misuse |
| ASI03 | Identity & Privilege Abuse |
| ASI04 | Agentic Supply Chain Vulnerabilities |
| ASI05 | Unexpected Code Execution |
| ASI06 | Memory & Context Poisoning |
| ASI07 | Insecure Inter-Agent Communication |
| ASI08 | Cascading Failures |
| ASI09 | Human-Agent Trust Exploitation |
| ASI10 | Rogue Agents |

## CWE-Top25-2025 (25)

| Id | Title |
|---|---|
| CWE-79 | Improper Neutralization of Input During Web Page Generation ('Cross-site Scripting') |
| CWE-89 | Improper Neutralization of Special Elements used in an SQL Command ('SQL Injection') |
| CWE-352 | Cross-Site Request Forgery (CSRF) |
| CWE-862 | Missing Authorization |
| CWE-787 | Out-of-bounds Write |
| CWE-22 | Improper Limitation of a Pathname to a Restricted Directory ('Path Traversal') |
| CWE-416 | Use After Free |
| CWE-125 | Out-of-bounds Read |
| CWE-78 | Improper Neutralization of Special Elements used in an OS Command ('OS Command Injection') |
| CWE-94 | Improper Control of Generation of Code ('Code Injection') |
| CWE-120 | Buffer Copy without Checking Size of Input ('Classic Buffer Overflow') |
| CWE-434 | Unrestricted Upload of File with Dangerous Type |
| CWE-476 | NULL Pointer Dereference |
| CWE-121 | Stack-based Buffer Overflow |
| CWE-502 | Deserialization of Untrusted Data |
| CWE-122 | Heap-based Buffer Overflow |
| CWE-863 | Incorrect Authorization |
| CWE-20 | Improper Input Validation |
| CWE-284 | Improper Access Control |
| CWE-200 | Exposure of Sensitive Information to an Unauthorized Actor |
| CWE-306 | Missing Authentication for Critical Function |
| CWE-918 | Server-Side Request Forgery (SSRF) |
| CWE-77 | Improper Neutralization of Special Elements used in a Command ('Command Injection') |
| CWE-639 | Authorization Bypass Through User-Controlled Key |
| CWE-770 | Allocation of Resources Without Limits or Throttling |

## ASVS 5.0.0 L2 verification families

Grouping rule (one rule): a family is one ASVS section (`section_id`, the first two numeric parts of the requirement id, e.g. `V1.2` holds `V1.2.1`..`V1.2.n`), restricted to its requirements with `L` <= 2. A section with no L<=2 requirement has no family. A family's eval covers all its members; a member judged (c) is labelled separately. Result: 75 families over 253 requirements. Per-requirement family is the `family` field in `items.json`.

| Family | Chapter | Section | Reqs |
|---|---|---|---|
| V1.1 | Encoding and Sanitization | Encoding and Sanitization Architecture | 2 |
| V1.2 | Encoding and Sanitization | Injection Prevention | 9 |
| V1.3 | Encoding and Sanitization | Sanitization | 11 |
| V1.4 | Encoding and Sanitization | Memory, String, and Unmanaged Code | 3 |
| V1.5 | Encoding and Sanitization | Safe Deserialization | 2 |
| V2.1 | Validation and Business Logic | Validation and Business Logic Documentation | 3 |
| V2.2 | Validation and Business Logic | Input Validation | 3 |
| V2.3 | Validation and Business Logic | Business Logic Security | 4 |
| V2.4 | Validation and Business Logic | Anti-automation | 1 |
| V3.2 | Web Frontend Security | Unintended Content Interpretation | 2 |
| V3.3 | Web Frontend Security | Cookie Setup | 4 |
| V3.4 | Web Frontend Security | Browser Security Mechanism Headers | 6 |
| V3.5 | Web Frontend Security | Browser Origin Separation | 5 |
| V3.7 | Web Frontend Security | Other Browser Security Considerations | 2 |
| V4.1 | API and Web Service | Generic Web Service Security | 3 |
| V4.2 | API and Web Service | HTTP Message Structure Validation | 1 |
| V4.3 | API and Web Service | GraphQL | 2 |
| V4.4 | API and Web Service | WebSocket | 4 |
| V5.1 | File Handling | File Handling Documentation | 1 |
| V5.2 | File Handling | File Upload and Content | 3 |
| V5.3 | File Handling | File Storage | 2 |
| V5.4 | File Handling | File Download | 3 |
| V6.1 | Authentication | Authentication Documentation | 3 |
| V6.2 | Authentication | Password Security | 12 |
| V6.3 | Authentication | General Authentication Security | 4 |
| V6.4 | Authentication | Authentication Factor Lifecycle and Recovery | 4 |
| V6.5 | Authentication | General Multi-factor authentication requirements | 5 |
| V6.6 | Authentication | Out-of-Band authentication mechanisms | 3 |
| V6.8 | Authentication | Authentication with an Identity Provider | 4 |
| V7.1 | Session Management | Session Management Documentation | 3 |
| V7.2 | Session Management | Fundamental Session Management Security | 4 |
| V7.3 | Session Management | Session Timeout | 2 |
| V7.4 | Session Management | Session Termination | 5 |
| V7.5 | Session Management | Defenses Against Session Abuse | 2 |
| V7.6 | Session Management | Federated Re-authentication | 2 |
| V8.1 | Authorization | Authorization Documentation | 2 |
| V8.2 | Authorization | General Authorization Design | 3 |
| V8.3 | Authorization | Operation Level Authorization | 1 |
| V8.4 | Authorization | Other Authorization Considerations | 1 |
| V9.1 | Self-contained Tokens | Token source and integrity | 3 |
| V9.2 | Self-contained Tokens | Token content | 4 |
| V10.1 | OAuth and OIDC | Generic OAuth and OIDC Security | 2 |
| V10.2 | OAuth and OIDC | OAuth Client | 2 |
| V10.3 | OAuth and OIDC | OAuth Resource Server | 4 |
| V10.4 | OAuth and OIDC | OAuth Authorization Server | 11 |
| V10.5 | OAuth and OIDC | OIDC Client | 5 |
| V10.6 | OAuth and OIDC | OpenID Provider | 2 |
| V10.7 | OAuth and OIDC | Consent Management | 3 |
| V11.1 | Cryptography | Cryptographic Inventory and Documentation | 2 |
| V11.2 | Cryptography | Secure Cryptography Implementation | 3 |
| V11.3 | Cryptography | Encryption Algorithms | 3 |
| V11.4 | Cryptography | Hashing and Hash-based Functions | 4 |
| V11.5 | Cryptography | Random Values | 1 |
| V11.6 | Cryptography | Public Key Cryptography | 1 |
| V12.1 | Secure Communication | General TLS Security Guidance | 3 |
| V12.2 | Secure Communication | HTTPS Communication with External Facing Services | 2 |
| V12.3 | Secure Communication | General Service to Service Communication Security | 4 |
| V13.1 | Configuration | Configuration Documentation | 1 |
| V13.2 | Configuration | Backend Communication Configuration | 5 |
| V13.3 | Configuration | Secret Management | 2 |
| V13.4 | Configuration | Unintended Information Leakage | 5 |
| V14.1 | Data Protection | Data Protection Documentation | 2 |
| V14.2 | Data Protection | General Data Protection | 4 |
| V14.3 | Data Protection | Client-side Data Protection | 3 |
| V15.1 | Secure Coding and Architecture | Secure Coding and Architecture Documentation | 3 |
| V15.2 | Secure Coding and Architecture | Security Architecture and Dependencies | 3 |
| V15.3 | Secure Coding and Architecture | Defensive Coding | 7 |
| V16.1 | Security Logging and Error Handling | Security Logging Documentation | 1 |
| V16.2 | Security Logging and Error Handling | General Logging | 5 |
| V16.3 | Security Logging and Error Handling | Security Events | 4 |
| V16.4 | Security Logging and Error Handling | Log Protection | 3 |
| V16.5 | Security Logging and Error Handling | Error Handling | 3 |
| V17.1 | WebRTC | TURN Server | 1 |
| V17.2 | WebRTC | Media | 4 |
| V17.3 | WebRTC | Signaling | 2 |

## Costed pilot plan: OWASP API Security Top 10:2023

Why this list: 10 items, the smallest list that still needs all three statuses (a), (b) and (c), and its items map onto detectors that already exist in `.claude/skills/deep-code-review/scripts` and `templates/semgrep-taint`. The proposed statuses below are a plan, not results; the independent audit lane may reject any of them, and a rejected label counts as unstatused.

| Item | Proposed | Backing detector or reason |
|---|---|---|
| API1:2023 Broken Object Level Authorization | (b) | `tenant_scope_check.py` covers only Prisma schemas with a tenant column, so it is a lead for one stack, not a detector for the item. Guided step: per-handler ownership check on object ids. |
| API2:2023 Broken Authentication | (a) candidate, fallback (b) | `attempt_limit_map.py` (no attempt limit on password and one-time-code checks), `csrf_cookie_map.py` (session cookie flags), semgrep `perun.js.auth-cookie-flags`. They cover only part of the item, so audit risk is high; plan (b) if the seeded tests cannot show the full item. |
| API3:2023 Broken Object Property Level Authorization | (b) | No detector for mass assignment or over-broad serializers. Guided step: compare response and write schemas with the caller's rights. |
| API4:2023 Unrestricted Resource Consumption | (a) | `cost_limit_map.py` (CWE-770/400, no rate or quota evidence), semgrep `perun.js.body-cap-after-buffer`. Runtime limit values are not static; the report names `dynamic_probe.py --rate-endpoint`. |
| API5:2023 Broken Function Level Authorization | (b) | `route_auth_map.py` finds handlers with no identity check (missing authentication), not wrong-role access. Guided step: role matrix against the admin and privileged routes; the script lists them. |
| API6:2023 Unrestricted Access to Sensitive Business Flows | (c) | Reason: process-only (which flows are sensitive and what abuse rate is tolerable is a business decision). Runtime check named in the report: run a scripted abuse test of the purchase, signup and referral flows against a staging system. |
| API7:2023 Server Side Request Forgery | (a) | Semgrep `perun.py.ssrf` and `perun.js.ssrf` (bundled taint rules). |
| API8:2023 Security Misconfiguration | (a) | `header_config.py`, semgrep `perun.js.cors-credentials-any-origin`, and the hub tools checkov and hadolint through `review_checks.sh`. Deployed-environment settings are out of static scope; the report names `dynamic_probe.py` (headers) against the running app. |
| API9:2023 Improper Inventory Management | (c) | Reason: deployed config (which versions and hosts are exposed is not in the repo). Runtime check: diff `route_auth_map.py --all` output against the gateway's live route list. |
| API10:2023 Unsafe Consumption of APIs | (b) | Semgrep `perun.js.fetch-no-timeout` is a partial lead only. Guided step: validate and bound third-party responses before use. |

Expected tally if every proposal stands: (a) 4 (API2, API4, API7, API8), (b) 4 (API1, API3, API5, API10), (c) 2 (API6, API9). (c) is 20%, under the 40% cap.

Cost estimate (agent calls; an ESTIMATE from the per-item work below, not a measurement; it has not been compared with the G8 line, which this file does not read):

- (a) item: 1 call to author the seeded positive and negative cases, 1 to run and fix, 1 spare = ~3. Four items = ~12. Items backed by an existing detector reuse its fixtures where present, so this is an upper bound.
- (b) item: 1 call to write the guided step, 1 blind author for the eval (2 positives, 1 negative), 2 runs (with the step, ablated) = ~4. Four items = ~16.
- (c) item: 1 call to write the runtime-check wording = ~1. Two items = ~2.
- Independent audit lane on a different model: all (c) labels plus a random 20% of the (a)/(b) labels (2 of 8 here) = ~4 calls.
- Total: about 34 agent calls, with a plausible range of 30 to 45. Scaling this per-item rate linearly to all 318 items would be misleading: ASVS items share one eval per family (75 families, not 253 evals), and the Top lists overlap in detectors. A full-matrix estimate should be re-derived from the pilot's measured calls, not from this figure.
