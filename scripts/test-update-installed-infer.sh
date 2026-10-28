#!/usr/bin/env bash
# update-installed.sh on a pre-marker install: infers flags from installed skills, writes the marker, says so.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
W="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-uii.XXXXXX")"; trap 'rm -rf "$W"' EXIT
mkdir -p "$W/h/scripts" "$W/h/.claude/skills/deep-code-review" "$W/t/.claude/skills/"{deep-code-review,agentic-delivery,idea-critic}
cp "$ROOT/scripts/update-installed.sh" "$W/h/scripts/"
echo 1.0.0 >"$W/h/.claude/skills/deep-code-review/VERSION"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$@" >"${@: -1}/.claude/ran-flags"\n' >"$W/h/install.sh"
out="$(DCR_NO_PULL=1 bash "$W/h/scripts/update-installed.sh" "$W/t" 2>&1)"
m="$W/t/.claude/.dcr-install-flags"
grep -qx -- --with-delivery "$m" && grep -qx -- --with-critic "$m" && [ "$(wc -l <"$m" | tr -d ' ')" = 2 ] \
  && grep -q "inferred flags: --with-delivery --with-critic" <<<"$out" \
  && grep -qx -- --with-delivery "$W/t/.claude/ran-flags" || { echo "FAIL infer: $out"; exit 1; }
# an older checkout without vendor_drift.py: skipped with one note, never "No such file"
grep -q "vendor_drift.py absent" <<<"$out" && ! grep -q "No such file" <<<"$out" || { echo "FAIL missing vendor_drift.py: $out"; exit 1; }
mkdir -p "$W/e/.claude"
if DCR_NO_PULL=1 bash "$W/h/scripts/update-installed.sh" "$W/e" >/dev/null 2>&1; then echo "FAIL: empty target must error"; exit 1; fi
echo "ok"
