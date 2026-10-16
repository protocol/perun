# Compatibility & portability — supported environments, co-existence, install and replace (domain I)

Read this when the target declares or implies a support matrix (browsers, operating systems, runtimes, database or OS versions, CPU architectures), ships something others install (a CLI, package, image, extension, plugin or agent skill), runs next to other software in a shared environment, or the ask is portability or vendor switching. ISO/IEC 25010:2023 splits this ground into Compatibility (co-existence, interoperability) and Flexibility (adaptability, scalability, installability, replaceability). Interoperability and contract evolution are `api-contracts.md`, and scalability is routed from `code-structure.md`; this file covers the rest.

## Declared, tested, actual

Find every place the target states what it supports, then compare three sets: declared, tested in CI, and what the code needs.

- **Where it is declared:** `engines`, `browserslist`, `requires-python` or `python_requires`, the `go` directive, `rust-version`, `.nvmrc` or `.tool-versions`, Dockerfile base images, documentation.
- **Where it is tested:** the CI matrix (runtime versions, operating systems, architectures, browsers).
- **Gap rules:** a declared range wider than the tested matrix is an unverified support claim, and a tested matrix with no declaration leaves users guessing.
- **npm `engines` is advisory.** The npm documentation calls the field "advisory only" unless the user has set the `engine-strict` config flag, and says it "will only produce warnings" when the package is installed as a dependency. A declared Node range is not enforced by installing.
- **Browserslist** is one shared config of target browsers read by tools such as Autoprefixer and Babel (its README). With no config the tools fall back to `defaults`, defined as `> 0.5%, last 2 versions, Firefox ESR, not dead`, so the real browser floor is whatever that resolves to on build day and moves with the data.
- **Baseline** (web.dev) is a usable yardstick for "can this CSS or JavaScript feature ship without a fallback": a feature is "widely available" once 30 months have passed since all the core browsers (Chrome, Edge, Firefox, Safari) supported it. Read the target's own support policy first (principle 5 in `SKILL.md`) and cite a Baseline status, not a memory.
- 🚩 a feature used with no support-matrix entry; `engines` wider than the CI matrix; an end-of-life runtime in the matrix (`dependency-currency-and-upgrades.md`).

## Environment portability probes (grep, then reproduce on the other platform)

- **Case and paths.** Imports or file references that differ only by letter case work on a case-insensitive filesystem and fail on a case-sensitive one. The common defaults are case-insensitive on macOS and Windows and case-sensitive on Linux; confirm the CI runner's. Also literal `/` or `\` joins instead of the platform path API, and hard-coded `/tmp`, `~` or drive letters.
- **Line endings.** Git normalises text files to LF in the index when `text` or `text=auto` is set in `.gitattributes`, and `eol=crlf` or `eol=lf` chooses the working-tree ending (git documentation). A repo with shell scripts and no such rule can check out a CRLF script on Windows that then fails under `bash`. 🚩 no `.gitattributes` in a cross-platform repo that ships scripts.
- **Shell and tools.** GNU against BSD flags (`lang-shell.md`); tools assumed to be on `PATH`.
- **CPU architecture.** An image, native module or prebuilt binary built for only one of amd64 and arm64.
- **Locale, time zone, terminal.** An assumed locale or zone (`time-date-correctness.md`, `i18n-l10n.md`), colour or prompt output with no TTY.
- **Network and ports.** Hard-coded `localhost`, and fixed ports that collide when two instances run.

## Co-existence (sharing an environment without harming other software)

- Writes outside the product's own directory: dotfiles in `$HOME`, shell profiles, global git config, `PATH` edits, global package installs.
- Fixed temp names, lock files, sockets or ports that collide across instances or users.
- Library code that patches globals or prototypes, and unscoped CSS in an embeddable widget.
- Two major versions of one library in a bundle, and peer-dependency conflicts.
- For installable behaviour (a skill, plugin, hook or daemon) the trust side is `security-agent-skills.md`; here the question is only whether it leaves other software working.

## Installability

- Install is idempotent: a second run is safe.
- Uninstall removes only what install added, tracked by a marker rather than by guessing.
- There is an upgrade path from the previous version that carries existing state and config.
- No root or network unless stated; a `--dry-run` and a non-interactive mode for CI; meaningful exit codes.
- 🚩 an uninstall that leaves residue or deletes user files; an installer that edits shared config with no marker; an upgrade that needs a manual state fix; `curl | sh` with no checksum (`appsec-supply.md`).

## Replaceability and lock-in

Apply this only where switching cost is high: the datastore, identity, payments, messaging, a model provider. Look for a documented and tested export path, and for standard formats and protocols instead of proprietary SDK types leaking into domain code (`code-structure.md`, dependency direction). Do not recommend an abstraction layer over a single dependency whose switching cost is low: a wrong abstraction costs more than three similar lines (`domain-h.md`).

## Rating

A declared-supported environment that is broken is High, because the claim is false for real users. A co-existence side effect that damages the user's other files or configuration is High. The rest is Medium or Low, calibrated by stage.
