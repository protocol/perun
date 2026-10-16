#!/usr/bin/env bash
# Test: host-native install manifests (Codex plugin + marketplace, Gemini extension) are valid JSON, carry the
# release version, and point at paths that exist. Their stamping by land-release.sh is covered by the version gate.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ver=$(cat .claude/skills/deep-code-review/VERSION)
python3 - "$ver" <<'PY'
import json, os, sys
ver = sys.argv[1]
def load(p): return json.load(open(p))
cx, mk, gm = load(".codex-plugin/plugin.json"), load(".agents/plugins/marketplace.json"), load("gemini-extension.json")
assert cx["name"] == "perun" and cx["version"] == ver, "codex plugin name/version"
assert os.path.isdir(cx["skills"]), "codex skills path must exist"
assert gm["name"] == "perun" and gm["version"] == ver, "gemini name/version"
assert os.path.isfile(gm["contextFileName"]), "gemini contextFileName must exist"
(e,) = mk["plugins"]
assert e["name"] == cx["name"] and e["source"] == {"source": "local", "path": "./"}, "marketplace source"
assert e["category"] and {"installation", "authentication"} <= set(e["policy"]), "marketplace policy/category"
print("PASS  host manifests valid, version", ver)
PY
