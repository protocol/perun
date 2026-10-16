#!/usr/bin/env bash
# Host command hints: context_nudge.py names the running agent host's own session commands at the context threshold,
# and a model/effort tier when the prompt's work kind changes, in two lines at most, never listing a command the
# vendor docs do not show. Runs the real hook per host with a scrubbed env; fixtures under TMPDIR; nothing is deleted
# or killed. The expected commands below are written from the vendor docs (docs/standards-index.md), not from the
# script's table, so a table edit that adds an undocumented command fails here.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NUDGE="$ROOT/.claude/skills/agentic-delivery/scripts/context_nudge.py"
TIER_DOC="$ROOT/.claude/skills/deep-code-review/references/model-tiering.md"
W="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-hch.XXXXXX")"
fail=0; n=0; pass=0
ok() { n=$((n+1)); if [ "$1" -eq 0 ]; then pass=$((pass+1)); echo "PASS  $2"; else echo "FAIL  $2"; fail=1; fi; }

transcript() { printf '{"type":"assistant","message":{"usage":{"input_tokens":2,"cache_read_input_tokens":%s,"cache_creation_input_tokens":0}}}\n' "$(($2 - 2))" >"$1"; }
transcript "$W/hot.jsonl" 300000   # over the 250k default threshold
transcript "$W/low.jsonl" 10000    # under 50k: no switch-cost clause, no threshold
hook() {  # hook <transcript> <session> <prompt> [VAR=val ...]: the hook's stdout under a scrubbed env plus the given variables
  local tr="$1" sid="$2" prompt="$3"; shift 3
  printf '{"transcript_path":"%s","session_id":"%s","prompt":"%s"}' "$tr" "$sid" "$prompt" |
    env -i PATH="$PATH" HOME="$W" XDG_CACHE_HOME="$W/cache" "$@" python3 "$NUDGE"
}
lines() { if [ -z "$1" ]; then echo 0; else printf '%s\n' "$1" | wc -l | tr -d ' '; fi; }
has() { case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac; }  # has <text> <literal>

# host_case <label> <display name> <env assignment> <commands that must appear | ...> <commands that must not | ...> <switch commands | ...>
host_case() {
  local label="$1" name="$2" envv="$3" must="$4" not="$5" sw="$6" out l2 c IFS='|'
  out="$(hook "$W/hot.jsonl" "$label-hot" "continue" "$envv")"
  [ "$(lines "$out")" -eq 2 ]; ok $? "$label: two lines at the threshold"
  l2="$(printf '%s\n' "$out" | sed -n 2p)"
  case "$l2" in "$name commands:"*) ok 0 "$label: line 2 opens with '$name commands:'" ;; *) ok 1 "$label: line 2 opens with '$name commands:' ($l2)" ;; esac
  has "$out" "handoff.md"; ok $? "$label: line 1 still asks for the handoff"
  for c in $must; do has "$l2" "$c"; ok $? "$label: lists $c"; done
  for c in $not; do has "$l2" "$c"; [ $? -ne 0 ]; ok $? "$label: does not list $c (not in its docs)"; done
  [ -z "$(hook "$W/low.jsonl" "$label-low" "continue" "$envv")" ]; ok $? "$label: silent below the threshold"
  out="$(hook "$W/low.jsonl" "$label-kind" "Run a security review of the auth change" "$envv")"
  [ "$(lines "$out")" -eq 1 ]; ok $? "$label: hard prompt prints one line"
  has "$out" "top-tier model at high effort"; ok $? "$label: hard prompt advises the top tier at high effort"
  has "$out" "switch back to the mid tier"; ok $? "$label: hard prompt says to switch back"
  for c in $sw; do has "$out" "$c"; ok $? "$label: hard prompt line carries $c"; done
  [ -z "$(hook "$W/low.jsonl" "$label-kind" "another P0 data-integrity bug" "$envv")" ]; ok $? "$label: same kind again is silent"
  out="$(hook "$W/low.jsonl" "$label-kind" "Rebase onto main" "$envv")"
  has "$out" "cheapest model at low effort"; ok $? "$label: kind change to mechanical advises cheapest at low effort"
  [ "$(lines "$out")" -eq 1 ]; ok $? "$label: kind change prints one line"
  out="$(hook "$W/hot.jsonl" "$label-both" "threat model the upload path" "$envv")"
  [ "$(lines "$out")" -eq 2 ]; ok $? "$label: threshold plus kind change is still two lines"
}

host_case claude-code "Claude Code" CLAUDECODE=1 "/compact|/autocompact|/clear|/context|/usage|/cost|/resume|/model|/effort" "/compress|/summarize" "/model|/effort"
host_case codex "Codex CLI" PERUN_HOST=codex "/compact|/clear|/new|/status|/usage|/resume|/model" "/effort|/reasoning|/compress|/context" "/model"
host_case gemini "Gemini CLI" GEMINI_SESSION_ID=abc "/compress|/clear|/stats|/resume|/model" "/compact|/effort|/usage|/context" "/model"
host_case copilot "Copilot CLI" PERUN_HOST=copilot "/compact|/clear|/new|/context|/usage|/resume|/model" "/effort|/reasoning|/compress|/stats" "/model"
host_case cursor "Cursor CLI" CURSOR_VERSION=2.0 "/summarize|/clear|/resume|/model" "/compact|/usage|/context|/stats|/effort" "/model"
host_case opencode "OpenCode" PERUN_HOST=opencode "/compact|/new|/sessions|/models|opencode stats|ctrl+t" "/usage|/cost|/stats|/effort|/compress|/context" "/models|ctrl+t"
host_case qwen "Qwen Code" QWEN_PROJECT_DIR=/p "/compress|/clear|/context|/stats|/resume|/model|/effort" "/compact|/cost" "/model|/effort"

# Detection edges.
out="$(hook "$W/hot.jsonl" gem-shell "continue" GEMINI_CLI=1)"; has "$out" "Gemini CLI commands:"; ok $? "GEMINI_CLI=1 (shell-tool marker) selects Gemini CLI"
out="$(hook "$W/hot.jsonl" pin "continue" CLAUDECODE=1 PERUN_HOST=codex)"; has "$out" "Codex CLI commands:"; ok $? "PERUN_HOST wins over a marker"
out="$(hook "$W/hot.jsonl" none "continue")"
[ "$(lines "$out")" -eq 1 ] && has "$out" "handoff.md" && ! has "$out" "/compact" && ! has "$out" "/clear"; ok $? "unknown host: the handoff line only, no commands"
out="$(hook "$W/hot.jsonl" two "continue" CLAUDECODE=1 CURSOR_VERSION=2.0)"
[ "$(lines "$out")" -eq 1 ]; ok $? "markers of two hosts: unknown, handoff line only"
out="$(hook "$W/hot.jsonl" bogus "continue" CLAUDECODE=1 PERUN_HOST=bogus)"
[ "$(lines "$out")" -eq 1 ]; ok $? "unknown PERUN_HOST value: unknown, handoff line only"
out="$(hook "$W/low.jsonl" unk-kind "security review please")"
has "$out" "top-tier model at high effort" && [ "$(lines "$out")" -eq 1 ] && ! has "$out" "/model"; ok $? "unknown host: tier advice without a switch command"
out="$(hook "$W/low.jsonl" neutral "thanks, continue" CLAUDECODE=1)"; [ -z "$out" ]; ok $? "a prompt naming no work kind stays silent"
out="$(hook "$W/low.jsonl" judge "the rebase failed, debug it" CLAUDECODE=1)"; [ -z "$out" ]; ok $? "a judgment prompt that merely mentions rebase is not mechanical"
out="$(hook "$W/hot.jsonl" cost "security review please" CLAUDECODE=1)"
has "$out" "re-reads the 300k-token context uncached"; ok $? "Claude Code, large context: the switch cost is stated"
out="$(hook "$W/hot.jsonl" cost-g "security review please" PERUN_HOST=gemini)"
! has "$out" "uncached"; ok $? "other hosts: no cache claim the docs do not support"

# The tier table in the script is the routing table in model-tiering.md.
python3 -I - "$NUDGE" "$TIER_DOC" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("context_nudge", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
doc = open(sys.argv[2], encoding="utf-8").read()
sec = doc.split("## Route delivery lanes by work type and stage", 1)[1].split("\n## ", 1)[0]
rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in sec.splitlines() if ln.startswith("|")]
bad = 0
for kind, prefix in (("mechanical", "Fully specified"), ("build", "Build, fix"), ("hard", "Security reviews")):
    row = next((r for r in rows if r[0].startswith(prefix)), None)
    got = (row[1].lower(), row[2].lower()) if row else None
    if got != mod.TIERS[kind]:
        bad = 1
        print(f"tier drift: {kind}: doc {got} != script {mod.TIERS[kind]}")
sys.exit(bad)
PY
ok $? "TIERS equals the routing table in model-tiering.md"

# The vendor pages the commands came from are recorded, dated.
sec="$(sed -n '/^## Verified by direct fetch (2026-10-16) — host session commands/,/^## /p' "$ROOT/docs/standards-index.md")"
miss=0
for u in code.claude.com/docs/en/commands developers.openai.com/codex/cli/slash-commands geminicli.com/docs/reference/commands \
         docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference cursor.com/docs/cli/reference/slash-commands \
         opencode.ai/docs/tui qwenlm.github.io/qwen-code-docs/en/users/features/commands; do
  has "$sec" "$u" || { miss=1; echo "standards-index.md lacks $u"; }
done
[ "$miss" -eq 0 ]; ok $? "docs/standards-index.md records all seven vendor command pages under a 2026-10-16 heading"

python3 "$NUDGE" --selftest >/dev/null; ok $? "context_nudge --selftest"
echo "Tests: $pass/$n passed"; exit "$fail"
