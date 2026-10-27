# Desktop and native apps: local IPC, binary hardening, updater trust

**Read this when** the target ships a desktop or native binary (Electron or other webview shell, Tauri, a system service or daemon, a CLI with an auto-updater, a plugin host). `mobile-appsec.md` covers phone IPC and `lang-c-cpp-rust.md` covers source-level memory bugs; this file holds what neither states. Treat each hit as a lead and run `appsec-verify.md` section 1 before reporting.

## 1. Local IPC is an untrusted network edge

Another local process, another local user, or a web page in the user's browser can reach every local endpoint. Apply `security-appsec.md` A01 to each one: enumerate all of them, then ask who the caller can be and what authorizes it.

- **Webview shells.** List every `ipcMain.handle`, `ipcMain.on`, Tauri command or exposed preload function. A handler that runs a command, reads or writes a path, or opens a URL from its argument is a sink; check that the renderer origin is validated in the handler, that the preload exposes narrow functions rather than the raw IPC channel, and that remote or user-generated content never loads in a window that has these bridges (look for `nodeIntegration`, a disabled `contextIsolation` or sandbox, a permissive navigation or `window.open` handler).
- **Localhost listeners.** A server bound to `0.0.0.0`, or to loopback with no per-session secret, is reachable from any local user and from browser pages (cross-origin requests, DNS rebinding). Look for a bearer token or a checked `Host` and `Origin`, not an open CORS policy.
- **Sockets, pipes, shared memory.** Check the file mode or ACL on a Unix socket or named pipe, and that the path is not in a world-writable directory with a predictable name (pre-creation and symlink races). Verify the peer identity where the platform offers it, instead of trusting a message field.
- **Custom URL schemes and file associations.** The handler receives attacker-chosen text from any web page or document. Parse it as untrusted, require confirmation for state-changing actions, and never pass it to a shell or a path join.
- **Privilege boundary.** A privileged helper or service that accepts requests from the unprivileged app must authorize each request itself; "only our app connects" is not a control.

## 2. Binary hardening and memory safety

For a shipped native binary, check what the build actually produced, not what the build file claims. Run a hardening inspection tool on the release artifact (`checksec`, `otool -hv`, `readelf -lW`, `dumpbin /headers`) and compare:

- Position-independent executable and ASLR, non-executable stack and data, stack protector, fortified libc calls, full RELRO or the platform equivalent, control-flow protection where the toolchain supports it. A missing mitigation on parsing code (archives, media, network protocols, document formats) is a finding; on code that handles no untrusted input it is a note.
- Memory-unsafe parsers fed untrusted bytes with no fuzz or sanitizer evidence in CI (`testing-situational.md` for fuzzing, `lang-c-cpp-rust.md` for sanitizers). A Rust `unsafe` block or a C dependency wrapped by FFI counts as memory-unsafe surface.
- Debug symbols, test hooks, a debug port or an unlocked developer menu left in the release build.
- Hardened-runtime and entitlement sets (macOS) or capability sets (Windows, Linux sandboxes) wider than the app uses: each entitlement is attack surface that a code-execution bug inherits.

## 3. Updater and release trust

The updater is a remote-code-execution channel into every install, so review it like a login flow.

- The client verifies a signature over the artifact (or a signed manifest naming the artifact digest) against a key shipped in the app. A hash fetched from the same server as the download, or TLS alone, proves nothing about the publisher.
- Downgrade and replay: the client refuses a lower version or an expired manifest, otherwise an attacker holding an old signed build can reinstall a known-vulnerable one.
- The signing key is not in the repository or a long-lived CI secret usable by any branch; release signing runs only on protected refs (`release-engineering.md`, signed releases; `appsec-supply.md` for the build inputs).
- OS-level trust: code signing and notarization (macOS), Authenticode (Windows) are applied to the shipped artifact, and the installer does not write to a user-writable path that a later elevated step executes.
- The update source is fixed in the signed binary, not read from a user-writable config or an environment variable.
- Findings from this section are `K` (build and release) with `B`; a missing check is a 🚩 only when the updater exists and the path to install is shown.
