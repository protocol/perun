# Mobile & native application security — OWASP MASVS/MASTG review

Read this when the target **is** (or ships) a native mobile client — an iOS
(Swift / Objective-C) or Android (Kotlin / Java) app, or a cross-platform client
(React Native, Flutter, .NET MAUI, Capacitor / Cordova) packaged as an
installable APK / IPA. It expands section B of `SKILL.md` for the `mobile`
archetype with the red flags **specific to code that runs on a user's device**.

**No duplication (the repo's thesis).** Web / API / CI-CD application security —
injection, generic access control, TLS-validation-disabled, server-side secret
hygiene, supply chain, logging — stays in `security-appsec.md`. This file does
**not** restate it; each section links to the `security-appsec.md` category it
extends and adds **only** the mobile delta. If a finding is the same class on a
server and a phone, cite it there.

Standard walked: **OWASP MASVS** (control groups verified this session) and its
testing companion **OWASP MASTG**. Group titles and the individual controls
quoted below are recorded, SHA-pinned, in `docs/standards-index.md` /
`references/standards-index.md` (after install). Where this file quotes a MASVS
control it is verbatim from the pinned source; everything else is this skill's
own mechanism-and-fix analysis, not a MASVS restatement.

---

## Why device-side is a different threat model (the one principle)

Every delta below reduces to one fact: **a mobile app's binary and its local
data live on hardware the attacker may control.** A server runs your code and
holds your secrets on infrastructure you own; a phone does not. Concretely, a
mobile reviewer must assume the attacker can:

1. **Possess the device** — a lost / stolen / seized / resold phone, or the
   user's own device under coercion or forensic extraction.
2. **Root / jailbreak it** — defeating the OS sandbox the app leans on, and
   **instrument** the running process (Frida / objection, a patched or
   repackaged binary) so any client-side check runs in attacker-controlled
   memory.
3. **Read the shipped binary** — the APK / IPA is distributed to every user and
   trivially unpacked (`strings`, `apktool`, `class-dump`, a disassembler), so
   anything compiled in is readable. **Compiled is not hidden.**
4. **Run other apps** on the same device that reach yours through platform IPC.
5. **Back the device up** — to a computer (`adb backup`, an unencrypted iTunes
   backup) or the cloud (Google / iCloud), moving app data off the device.

That is why "the sandbox keeps other apps out" and "storage is encrypted at
rest" are **not** the end of a mobile storage review, why a client-side
authorization check is worth nothing, and why a secret in the binary is public.
None of these adversaries exist for the server-side code in `security-appsec.md`.

**MASVS control groups (8, verified this session):** MASVS-STORAGE (storage),
MASVS-CRYPTO (cryptography), MASVS-AUTH (authentication & authorization),
MASVS-NETWORK (network communication), MASVS-PLATFORM (platform interaction),
MASVS-CODE (code quality), MASVS-RESILIENCE (resilience against reverse
engineering & tampering), MASVS-PRIVACY (privacy). The sections below map to
these; MASTG is the how-to-test companion for each.

---

## 1. Insecure local storage & key protection (MASVS-STORAGE-1/2, MASVS-CRYPTO-2)

MASVS-STORAGE-1, verbatim: *"The app securely stores sensitive data."*
MASVS-STORAGE-2, verbatim: *"The app prevents leakage of sensitive data."*

**Mechanism (why it bites on mobile).** Sensitive data — session / refresh
tokens, passwords, PII, encryption keys — written to a **plaintext client
store** is exposed to threats 1, 2 and 5 above, none of which a server faces.
The common plaintext stores:

- iOS: `UserDefaults` (`NSUserDefaults`) / `.plist` files, unencrypted Core Data
  or a raw SQLite DB, plain files in the app container.
- Android: `SharedPreferences`, plain files in internal storage, an unencrypted
  SQLite / Room DB; external storage / `MediaStore` was **world-readable to any
  app** pre-scoped-storage — under scoped storage (Android 10/11+) access is
  mediated, but shared/media collections and legacy paths still leak, so keep
  sensitive data off external storage entirely.

"It is in the app's private data directory, so only our app can read it" holds
**only on a non-compromised device**. On a rooted / jailbroken device, through a
device or cloud **backup**, or a forensic / physical extraction, the app-private
directory is readable, and a plaintext long-lived token walks off with it.

**"Encrypted at rest" is not app-level protection.** Full-disk / file-based
encryption (iOS Data Protection, Android FBE) protects data while the device is
**locked or powered-off**. Once the device is unlocked and the app can read its
own files, so can a privileged local adversary (root, a restored backup, an
instrumented process) — device encryption isolates the device from an outsider,
it does **not** isolate the app's own data from an on-device attacker. Do not
accept "the phone encrypts storage" as a reason to store a secret in plaintext.

**Keychain / Keystore is not automatically safe — the class and backing matter.**

- **iOS Keychain accessibility class.** A Keychain item's protection is set by
  its accessibility attribute. `kSecAttrAccessibleAlways` (deprecated) and
  `...AfterFirstUnlock` keep the item readable whenever the device has been
  unlocked once since boot — extractable from a seized or backed-up device.
  Prefer `...WhenUnlockedThisDeviceOnly` / `...WhenPasscodeSetThisDeviceOnly`:
  the `ThisDeviceOnly` suffix keeps the item off backups and bound to this
  device, and `WhenUnlocked` requires an unlocked device to read it.
- **Android Keystore backing.** A key in the AndroidKeyStore should be
  **hardware-backed** (TEE / StrongBox) so the key material never enters app
  memory, and for high-value use gated by `setUserAuthenticationRequired(true)`.
  A key kept in memory, in `SharedPreferences`, or in a software-only keystore
  has none of that protection. MASVS-CRYPTO-2 covers *"key management … key
  generation, storage and protection."*

**Fix.** Persist as little as possible — prefer **short-lived, server-revocable**
tokens over a long-lived credential on disk. Store what you must in the platform
**hardware-backed secure store** (iOS Keychain with a `...ThisDeviceOnly`
class; Android Keystore, hardware-backed, user-auth-bound where warranted).
Encrypt any local DB / files with a **Keystore/Keychain-wrapped** key (Android
`EncryptedSharedPreferences` / SQLCipher with a Keystore key; not a key
hardcoded or derived from a constant). Keep sensitive data off external storage
and out of backups (§7). This is a distinct control from server-side
"secrets via env / secret manager only" (`security-appsec.md` § Secrets) — that
guards **your infrastructure**; this guards **the user's device**.

---

## 2. Network: cleartext opt-outs and missing transport pinning (MASVS-NETWORK-1/2)

MASVS-NETWORK-1, verbatim: *"The app secures all network traffic according to the
current best practices."* MASVS-NETWORK-2, verbatim: *"The app performs identity
pinning for all remote endpoints under the developer's control."*

**(a) Cleartext via a declarative platform opt-out.** `security-appsec.md` A04
already sets "TLS enforced end-to-end (no plaintext transport of secrets)" — the
principle is there, do not restate it. The mobile delta is the **declarative
platform switch** that re-enables cleartext (or a rogue trust anchor) **without
touching any request code**, so a grep of application source never finds it:

- iOS `Info.plist` → `NSAppTransportSecurity` with `NSAllowsArbitraryLoads` = YES
  (or per-domain `NSExceptionAllowsInsecureHTTPLoads`) disables App Transport
  Security.
- Android `AndroidManifest.xml` `android:usesCleartextTraffic="true"`, or a
  `res/xml` **network security config** with `cleartextTrafficPermitted="true"`
  or a `<trust-anchors>` that adds a **`user`** CA to the production config
  (which lets any user-installed CA — including an interception proxy's —
  terminate TLS).

**Fix.** No arbitrary-loads ATS exception in a shipped build; per-domain
exceptions only, named and justified. `cleartextTrafficPermitted="false"`; no
`user` trust anchor in the production network security config (a debug-only
config via `debug-overrides` is fine). The finding lives in `Info.plist` /
`AndroidManifest.xml` / `res/xml`, not the networking layer.

**(b) Missing / bypassable pinning.** `security-appsec.md` A04 "TLS enforced is
not TLS validated" covers a client that **disables** validation (trust-any-cert,
`InsecureSkipVerify` etc., CWE-295) — **link that; it is the same bug on mobile**
and a grep for it applies. MASVS-NETWORK-2 is the **opposite** direction and is
mobile-specific: even with correct default validation, the app runs on a device
whose trust store the **user (or an attacker holding the device) can add a CA
to**, so a MITM proxy with a user-installed root intercepts traffic that passes
ordinary validation. Pinning trusts only your endpoint's specific public key /
certificate, defeating that.

**Mechanism nuance — pinning is a bar-raiser, not a channel-integrity
guarantee.** Because the app runs on a controlled device, pinning is bypassable
by instrumentation (Frida / objection unpin, patching the pin set). It protects
the honest user's traffic and defeats casual / network-level MITM; it does **not**
make the channel un-interceptable by a determined attacker who owns the device.
So (i) never treat "we pin" as a reason to trust the client channel for
authorization — the server still authenticates every request; and (ii) a pin
with **no backup pin and no rotation plan** bricks the app when the certificate
rotates (an availability self-DoS).

**Fix.** Pin under NETWORK-2 (Android `network-security-config` `<pin-set>`, or a
maintained pinning library; iOS pin the SPKI / certificate), keep a **backup
pin** and a short **rotation runbook**, and always combine with server-side
controls — pinning is defense in depth, not the boundary.

---

## 3. Exported components, IPC & implicit intents; deeplinks / app links (MASVS-PLATFORM-1)

MASVS-PLATFORM-1, verbatim: *"The app uses IPC mechanisms securely."*

**Mechanism.** This is `security-appsec.md` A01 applied to **on-device IPC**, not
network routes — so reuse A01's "enumerate every route **and non-route entry
points**", its "authorization decided only in the client = no authorization",
and its **dual-surface** rule (which already names *mobile clients* as a caller
class). **Link A01; do not re-derive those.** The mobile-specific facts A01 does
not state:

- An Android component (`activity` / `service` / `receiver` / `provider`) is
  reachable by **any other app on the device** when it is `exported` — declared
  `android:exported="true"`, or, on older targets, **implicitly** because it
  declares an `intent-filter`. (Android 12+ requires an explicit `exported` when
  a filter is present, but `intent-filter` + `exported="true"` remains common.)
  If such a component performs a sensitive action or returns sensitive data
  based on the incoming `Intent`'s extras **without verifying the caller or
  re-checking authorization**, a malicious app invokes it directly, bypassing the
  whole in-app flow.
- **Trusting an Intent-supplied id** (a document / account / order id in the
  extras) reproduces **IDOR**: re-authorize the id against the authenticated
  user **server-side**, exactly as A01's two-principal rule requires — the id in
  the Intent is attacker-controlled.
- An **implicit** intent or an ordered broadcast can be received, or its result
  read, by another app — sensitive data placed in an implicit intent leaks.
- A **`PendingIntent`** created **mutable** with an **implicit** base intent lets
  the receiving app fill in the blanks and act **with your app's identity and
  permissions**.
- A `content://` provider with `grantUriPermissions` / world read, or an exported
  provider over a private DB / file tree, exposes data to other apps.

**Deeplinks / custom schemes / app links.** A custom URL scheme (`myapp://…`) can
be **claimed by any app** (scheme hijacking), so it must never carry a secret
(e.g. an OAuth authorization code) or trigger a sensitive action on trust. Use
**verified Android App Links** (`android:autoVerify` + a hosted
`assetlinks.json`) / **iOS Universal Links** (a hosted
`apple-app-site-association`), which are domain-verified. A deeplink that lands on
an authenticated action must still require the **session** — the link is not the
credential. (Where a deeplink reflects a `next` / `returnTo`-style parameter, the
open-redirect class is `appsec-links.md` A01 CWE-601 — link it. OAuth/PKCE:
`appsec-tokens.md`.)

**Fix.** `exported="false"` unless the component is deliberately cross-app;
require a **signature-level** permission for cross-app entry points you own;
authenticate / validate the caller; re-authorize every id or action **server-side**
and never trust intent extras; create **immutable, explicit** `PendingIntent`s;
prefer verified App Links / Universal Links over raw custom schemes for anything
sensitive.

---

## 4. WebView JavaScript bridge & untrusted content (MASVS-PLATFORM-2)

MASVS-PLATFORM-2, verbatim: *"The app uses WebViews securely."* Its description
names the exact danger: *"sensitive functionality exposure (e.g. via JavaScript
bridges to native code)."*

**Mechanism.** A WebView that **both** (a) exposes a **native bridge** — Android
`addJavascriptInterface(obj, "name")` / `@JavascriptInterface` methods, iOS a
`WKScriptMessageHandler` — **and** (b) loads **untrusted or attacker-influenceable
content** (a remote page, a URL received via an intent / deeplink, mixed content,
or HTML built by concatenating unescaped data) hands web-origin JavaScript a path
to **native code and the app's permissions**. This is strictly worse than web XSS
(`security-appsec.md` A05, which is the base for the injection / escaping side —
link it): the sink is not the DOM, it is the **device**. Extra WebView footguns:

- `setJavaScriptEnabled(true)` while navigating to arbitrary / attacker-supplied
  URLs, or not restricting navigation in `shouldOverrideUrlLoading`.
- `setAllowFileAccessFromFileURLs(true)` / `setAllowUniversalAccessFromFileURLs(true)`
  letting a `file://` page read local files or reach any origin.
- Pre-API-17 `addJavascriptInterface` exposes **all public methods** of the bound
  object, including reflection → remote code execution.
- Loading, in the WebView, a URL delivered through IPC (§3).

**Fix.** Do not expose a native bridge to a WebView that can load remote /
untrusted content. If a bridge is genuinely required, load **only bundled,
integrity-checked local assets** over `https` / an app scheme, restrict
navigation to an allowlist, disable file / universal access, keep the bridge
surface minimal and **validate + authorize every message**, and never build the
page HTML by concatenating untrusted data (A05).

---

## 5. Client-only auth / biometric gate as the sole control (MASVS-AUTH-2/3)

MASVS-AUTH-2, verbatim: *"The app performs local authentication securely
according to the platform best practices."*

**Mechanism.** A "biometric / PIN gate", a feature entitlement, or a paywall that
is just a **local boolean the app tests** — `if (biometricSucceeded) {
doSensitiveThing() }`, `if (user.isPremium) { … }` — is **not** authorization.
The app runs in an attacker-controlled environment (threat 2), so on a rooted
device or via instrumentation the branch is forced true, the check is stubbed, or
the sensitive call is invoked directly. This is exactly `security-appsec.md` A01
"**authorization decided only in the client = no authorization**" — **link it**.
The mobile-specific *fix* is concrete and is what a review should require:

- A biometric prompt must gate the **release of a hardware-backed key**, not
  return a boolean: Android `BiometricPrompt` bound to a
  `setUserAuthenticationRequired` Keystore key via a `CryptoObject`; iOS a
  Keychain item guarded by `SecAccessControl` (`.biometryCurrentSet` /
  `.userPresence`). A passed check then **cryptographically unlocks a secret**;
  a bypassed check yields nothing usable.
- Every sensitive / paid / state-changing action is **authenticated and
  authorized server-side** — the client's assertion that "the user passed
  biometrics" or "the user is premium" is not proof. Entitlement / paywall
  checks belong on the server (or a signed receipt the server validates).

**Fix.** Bind biometrics to a Keystore / Keychain crypto object; enforce all
sensitive authorization on the server; treat the client as untrusted. Anti-tamper
does **not** substitute for this (§6).

---

## 6. Root/jailbreak detection & anti-tamper as the ONLY defense — theater (MASVS-RESILIENCE)

MASVS-RESILIENCE-1, verbatim: *"The app validates the integrity of the platform."*
Its description is explicit that resilience **supports** the other controls:
running on a tampered platform *"may disable certain security features"* and
*"Trusting the platform is essential for many of the MASVS controls relying on the
platform being secure (e.g. secure storage, biometrics, sandboxing, etc.)."*

**Mechanism.** RESILIENCE controls — root / jailbreak detection, anti-debug,
anti-hooking, integrity / signature checks, obfuscation — run **on the very
platform they distrust**, so a determined attacker who controls the device
bypasses them (Magisk DenyList, a Frida gadget, patching the check out). They are
legitimate **defense in depth** to raise the cost of attack. Two review errors:

- **(a) Treating resilience as a substitute for a real control.** "We detect
  root, so plaintext storage / a client-only auth gate is fine" is false — as
  RESILIENCE-1 itself says, resilience *validates the assumption* that STORAGE,
  CRYPTO, AUTH etc. rely on; it does not replace them. A data-protection gap
  (§1, §5) is not compensated by an anti-tamper check.
- **(b) Over-flagging its absence.** MASVS-RESILIENCE applies to apps that
  process **high-value assets** or face a meaningful reverse-engineering threat.
  A typical app is **not** deficient for lacking anti-tamper, and a review that
  demands root detection everywhere is **stricter than the standard** (see
  `full-map-principles.md` principle 4 (no harm) and the stage lens).

**Fix.** Keep resilience as **one layer**, never the boundary; never accept it as
compensating for a storage / auth / network gap; calibrate the *demand* for it to
the app's asset value and threat model.

---

## 7. Platform side-channel leakage (MASVS-STORAGE-2, MASVS-PLATFORM-3)

MASVS-PLATFORM-3, verbatim: *"The app uses the user interface securely,"* naming
leaks *"due to platform mechanisms such as auto-generated screenshots…"* These
are leak surfaces a server simply does not have:

- **App-switcher / background snapshot.** iOS screenshots the UI when the app
  backgrounds (shown in the app switcher and cached to disk); a screen showing
  secrets leaks. **Fix:** blank / obscure sensitive views on `willResignActive`
  (an overlay or hidden field). Android: set `FLAG_SECURE` on windows with
  sensitive content — it also blocks screenshots and screen recording.
- **Clipboard / pasteboard.** Copying a secret (OTP, token, card / account
  number) to the **global** clipboard exposes it to every app (and, with a
  universal clipboard, other devices). **Fix:** avoid it; mark sensitive iOS
  pasteboard items local / expiring; clear after use.
- **Logs.** `NSLog` / `Log.d(…)` of a token or PII is readable on-device via
  `adb logcat` (and by other apps pre-Android-4.1), and is captured by crash /
  analytics breadcrumbs. This overlaps `security-appsec.md` A09 (don't log
  secrets) — **link it**; the mobile delta is the **on-device reader** (adb,
  other apps) and third-party crash SDKs that snapshot the view hierarchy.
- **Backups.** Android `android:allowBackup="true"` (the historical default)
  lets `adb backup` / cloud backup exfiltrate app-private data to a machine; iOS
  files not excluded from iCloud / iTunes backup travel off-device. **Fix:**
  `allowBackup="false"` or `fullBackupContent` / backup rules that exclude
  sensitive files; on iOS set `isExcludedFromBackup` and keep secrets in the
  Keychain (a `ThisDeviceOnly` class, §1), not the file system.
- **Keyboard cache / third-party keyboards.** A non-secure text field is learned
  by autocorrect, and a third-party keyboard can exfiltrate keystrokes. **Fix:**
  mark secret fields secure (`isSecureTextEntry`; Android an appropriate
  password `inputType` + `textNoSuggestions`) and disable autocorrect on
  sensitive inputs.
- **Tapjacking / overlay.** Another app draws over yours to hijack taps (Android
  `SYSTEM_ALERT_WINDOW`). **Fix:** `setFilterTouchesWhenObscured(true)` /
  `android:filterTouchesWhenObscured` on sensitive controls. This is the mobile
  sibling of web clickjacking (frame-ancestors) — depth in `frontend-a11y.md`;
  link, don't restate.

---

## 8. Hardcoded secrets in the shipped binary (MASVS-CRYPTO-1) — link A04 + § Secrets

`security-appsec.md` A04 ("secrets not hard-coded") and its cross-cutting
**Secrets** section ("Nothing sensitive in source … secrets via env / secret
manager only") already state the rule — **link them; do not restate the fix.**
The **only** mobile-specific reasoning to add: the compiled app is **distributed
to every user** and trivially unpacked (threat 3), so a key, API secret, or
signing secret embedded in the binary or its resources is readable by **anyone
who installs the app** — not merely by someone with source access. Obfuscation
raises effort, it does not make extraction hard. A symmetric key or shared API
secret shipped client-side must therefore be treated as **public**: move the
trust to the server (a per-user token minted server-side, a server-side proxy for
the privileged call), never a shared client secret. MASVS-CRYPTO-1, verbatim:
*"The app employs current strong cryptography and uses it according to industry
best practices"* — a key everyone can read fails that regardless of the algorithm.

---

## 9. Excessive permissions & third-party SDK exfiltration (MASVS-PRIVACY) — domain Q

MASVS-PRIVACY-2, verbatim: *"The app prevents identification of the user,"*
warning against repurposing *"'fingerprint-like' signals (e.g. device IDs, IP
addresses, behavioral patterns)"* — its own example: *"a fingerprint used for
fraud detection should be isolated and not repurposed for audience measurement in
an analytics SDK."*

**Mechanism.** An app's declared and runtime-requested permissions define both
its attack surface and its privacy exposure. A bundled **third-party SDK**
(analytics, ads, attribution, crash reporting) runs **in the app's own process**
and **inherits every permission the user granted** — so an over-broad permission
set plus an opaque SDK is a data-exfiltration path (contacts, precise location,
clipboard, device identifiers) that the app's **own** code never shows.
`appsec-supply.md` A03 covers dependency provenance / pinning — **link it** for
the supply-chain base; the mobile / privacy delta is:

- **Least permission.** Request the minimum; prefer scoped / one-time grants and
  privacy-preserving APIs (approximate vs precise location, the system photo
  picker vs full-gallery read, avoid `QUERY_ALL_PACKAGES`).
- **SDK data inventory.** Know what each SDK collects and transmits; isolate a
  fingerprint-like signal to its stated purpose (PRIVACY-2 above).
- **Declaration matches behavior.** The store privacy declaration (Apple Privacy
  Nutrition Labels / Google Data Safety) must match what the app and its SDKs
  actually do.

Route legal / consent duties (GDPR, COPPA, ATT) to `privacy-compliance.md` and
counsel — this section is the code / behavior finding, not a compliance verdict.

---

## 🚩 grep / manifest tells (mobile-specific artifacts)

Read the **manifests and platform config**, not only the code — several of these
never appear in application source.

- **iOS.** `NSAllowsArbitraryLoads` / `NSExceptionAllowsInsecureHTTPLoads`
  (Info.plist); a Keychain `kSecAttrAccessibleAlways` / `...AfterFirstUnlock`
  **without** `ThisDeviceOnly`; `UserDefaults` / `NSUserDefaults` holding a
  token / password / PII; `WKScriptMessageHandler` / `addUserScript` on a
  WebView that `load`s a remote URL; `NSLog(` of a sensitive variable; a file
  written with no `isExcludedFromBackup`; a text field without
  `isSecureTextEntry`.
- **Android.** `android:usesCleartextTraffic="true"`,
  `cleartextTrafficPermitted="true"`, a `<trust-anchors>` `user` CA in the
  network-security config; `android:allowBackup="true"`;
  `android:exported="true"` (or an `intent-filter` with no explicit `exported`)
  on an activity / service / receiver / provider; `addJavascriptInterface(`,
  `setJavaScriptEnabled(true)`, `setAllowUniversalAccessFromFileURLs(true)`;
  `getSharedPreferences` / a plaintext SQLite DB holding secrets; `Log.d/e(` of
  a token; a **mutable** `PendingIntent` (`FLAG_MUTABLE`, or pre-`FLAG_IMMUTABLE`
  code); `SYSTEM_ALERT_WINDOW`; over-broad `<uses-permission>`
  (`READ_CONTACTS`, `ACCESS_FINE_LOCATION`, `QUERY_ALL_PACKAGES`).
- **Cross-platform.** A client-side `if (biometric…)` / `isJailbroken()` /
  `isPremium` check with no server enforcement; a pinning config with no backup
  pin; a secret string surfaced by `strings` on the shipped binary / resources.

**Going deeper:** MASTG (the testing companion) has per-platform test procedures,
a knowledge base, and vulnerable / secure demos for each MASVS group above; walk
the relevant group's MASTG tests when you need a proof procedure rather than a
review heuristic.
