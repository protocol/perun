#!/usr/bin/env bash
# install.sh — install deep-code-review (and optional overlays) into a project.
#
# Usage:
#   ./install.sh [--minimal] [--with-codex] [TARGET_DIR]
#   ./install.sh --with-delivery [--with-critic] [TARGET_DIR]
#   ./install.sh --full [TARGET_DIR]
#   ./install.sh --with-gates [TARGET_DIR]
#   ./install.sh --with-delivery --with-operating-layer [TARGET_DIR]
#   ./install.sh --recommend [TARGET_DIR]
#
# Default (agent-agnostic): copies the REVIEW skill into every common skill
# root the major hosts discover, and writes/refreshes a root AGENTS.md pointer:
#   - .agents/skills/deep-code-review/   (Agent Skills / open standard)
#   - .cursor/skills/deep-code-review/   (Cursor)
#   - .claude/skills/deep-code-review/   (Claude Code; Cursor/Codex also load)
# Optional hosts:
#   --with-codex         also .codex/skills/
#   --with-extra-hosts   also .gemini .opencode .github .windsurf .hermes .kiro .cline .roo .factory .qwen .grok
# Overlay skills (opt-in; default stays review-only):
#   --with-delivery      also agentic-delivery
#   --with-terse-replies with --with-delivery: write a Stop-hook snippet (terse_reply_check.py, opt-in)
#   --with-critic        also idea-critic
#   --with-comms         also communication-structure
#   --with-contribution  also contribution (prepare upstream PRs; not in --full)
#   --with-discovery     also product-discovery (worth-building / PMF / prioritization; not in --full)
#   --with-ceo           also agentic-ceo (suite conductor: routing + effort-sizing + chaos playbook; not in --full)
#   --with-growth        also growth-analytics (North Star + AARRR + event taxonomy; not in --full)
#   --with-positioning   also positioning (value prop / message house; a hypothesis, never fabricated market facts; not in --full)
#   --with-business      also business-ops (Lane A pricing/unit-economics apply vs Lane R legal/tax/securities route; not in --full)
#   --with-output-safety also product-output-safety (govern harm from the product's own AI outputs; HITL on high-stakes actions; not in --full)
#   --full               review + delivery + critic + comms
#   --recommend          inspect TARGET, print a pack, install nothing
# CI enforcement (mechanism, not a skill; opt-in; never overwrites a file):
#   --with-gates         also write .github/workflows/dcr-gates.yml +
#                         scripts/dcr-gates.sh, wiring the INSTALLED skill's
#                         own gate scripts (fix_class_gate, binaries_gate)
#                         into the target's own CI; and .githooks/pre-push, a
#                         local hook that reruns the fast lint+unit tier
#                         before every push (opt in yourself: git config
#                         core.hooksPath .githooks -- never run by this
#                         script). Prints (does not write) a settings.json
#                         snippet for agentic-delivery's two-tier SubagentStop
#                         handback_cap hook and its SubagentStart
#                         subagent_start_inject hook.
# Narrow:
#   --minimal            only .claude/skills/ + AGENTS.md
#   --claude-only        only .claude/skills/ ; skip AGENTS.md
#   --with-cursor        no-op (Cursor path is now part of the default set)
#
# Source of truth in the upstream repo remains the trees under
# .claude/skills/<name>/ — install copies *from* there; never duplicates
# a skill inside the upstream repository itself.
#
# Backups land under <TARGET>/.<host>/skill-backups/ —
# never inside skills/, so backups are never loaded as duplicate skills.
# No network, no sudo, fully local and reversible.

set -euo pipefail

usage() {
  cat >&2 <<'EOF'
install.sh — install deep-code-review for any coding agent.

Usage:
  ./install.sh [--minimal] [--with-codex] [--claude-only] [TARGET_DIR]
  ./install.sh --with-delivery [--with-critic] [TARGET_DIR]
  ./install.sh --full [TARGET_DIR]
  ./install.sh --recommend [TARGET_DIR]

Default: install REVIEW ONLY into .agents/skills/, .cursor/skills/, and
.claude/skills/, plus an AGENTS.md pointer (version-stamped; refreshed
on re-install). Overlay skills are opt-in.

  --minimal            Only .claude/skills/ + AGENTS.md
  --policy dim=value[,dim=value]  Write .perun/policy.json (e.g. local_cpu=maximize,github_actions=off,share_learnings=auto;
                       role=ceo warns and role=ceo-strict blocks when the MAIN session hand-edits source, never a subagent)
  --with-codex         Also .codex/skills/
  --with-extra-hosts   Also Gemini, OpenCode, Copilot, Windsurf, Hermes, Kiro, Cline, Roo Code, Factory Droid, Qwen Code, Grok Build
  --claude-only        Only .claude/skills/; skip AGENTS.md
  --with-cursor        Accepted as no-op (Cursor path is default now)
  --with-delivery      Also install agentic-delivery (gated delivery overlay)
  --with-terse-replies With --with-delivery: write a Stop-hook snippet that asks for terser rewrites (opt-in)
  --with-critic        Also install idea-critic (pre-owner idea attack)
  --with-comms         Also install communication-structure (BLUF messages)
  --with-contribution  Also install contribution (prepare upstream PRs; default off, not in --full)
  --with-discovery     Also install product-discovery (worth-building / PMF / prioritization; default off, not in --full)
  --with-ceo           Also install agentic-ceo (suite conductor: routing, effort-sizing, chaos playbook; default off, not in --full)
  --with-growth        Also install growth-analytics (North Star + AARRR + event taxonomy; default off, not in --full)
  --with-positioning   Also install positioning (value prop / message house; a hypothesis, never fabricated market facts; default off, not in --full)
  --with-business      Also install business-ops (Lane A pricing/unit-economics apply vs Lane R legal/tax/securities route; default off, not in --full)
  --tracker-project ID Write a <=12-line "Work tracking" block into AGENTS.md (idempotent; replayed by update-installed)
  --tracker NAME       Tracker for that block: linear (default), github or jira
  --with-output-safety Also install product-output-safety (govern harm from the product's own AI outputs; HITL on high-stakes actions; default off, not in --full)
  --full               Review + delivery + critic + comms
  --with-gates         Write .github/workflows/dcr-gates.yml + scripts/dcr-gates.sh,
                       wiring the INSTALLED skill's own gate scripts (fix_class_gate,
                       binaries_gate) into the target's own CI, plus
                       .githooks/pre-push (reruns the fast lint+unit tier before every
                       push -- opt in yourself with `git config core.hooksPath
                       .githooks`, never run by this script); never overwrites an
                       existing file at any of these paths (writes .new instead).
                       See --with-operating-layer for the SubagentStart/SubagentStop
                       settings snippet. Mechanism, not a skill.
  --no-operating-layer Opt out of the default-on operating layer (applied with --with-delivery/--full).
  --with-operating-layer
                       Write .claude/settings.operating-layer.json.new: the
                       heavy_gate.py PreToolUse and session_brief.py SessionStart hooks, the
                       ceo_altitude_guard.py hook (counts always, warns/blocks only once policy role is set), the
                       SubagentStart house-default injector, the two-tier
                       SubagentStop handback_cap, and the subagent model pin
                       (agentic-delivery/references/operating-discipline.md).
                       Never overwrites an existing file at that path (writes
                       .new-1, .new-2, ... instead). Requires --with-delivery.
  --apply-operating-layer
                       Instead of writing a .new snippet, jq-merge the operating-layer
                       hooks/env (plus model "sonnet" if unset) into
                       TARGET/.claude/settings.local.json idempotently (backup first;
                       fails closed if jq is missing) and write
                       .claude/agents/delivery-lane.md if absent. Implies
                       --with-operating-layer; requires --with-delivery.
  --no-sandbox         Leave the sandbox and deny rules OUT of the operating layer.
                       By default it sets sandbox.enabled=true,
                       sandbox.allowUnsandboxedCommands=false and denies
                       Bash(rm -rf *), (rm -fr *), (rm -r *), (rm -R *), (sudo *).
                       RISK: without the OS sandbox nothing stops an agent's
                       `rm -rf "$EMPTY"/*` from deleting your files; deny rules
                       match command text only (bypassable via /bin/rm, bash -c).
  --no-auto-update     Write auto_update: "off" to TARGET/.perun/policy.json. By default the
                       operating layer's SessionStart/UserPromptSubmit hook checks the newest
                       vX.Y.Z tag at most every 6h in the background and re-applies this
                       install from it (scripts/update-installed.sh; your settings win).
  --recommend          Inspect TARGET and print a recommended pack; no writes
  -h, --help           Show this help

TARGET_DIR defaults to the current working directory.

An agent should run --recommend, tell the owner the pack, and wait for a
yes before --with-delivery / --full. Default install stays review-only so
a second delivery OS already in the project is not doubled.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REVIEW_NAME="deep-code-review"

WRITE_AGENTS=1
MINIMAL=0
WITH_CODEX=0
WITH_EXTRA=0
WITH_DELIVERY=0
NO_SANDBOX=0
WITH_CRITIC=0
WITH_COMMS=0
WITH_CONTRIBUTION=0
WITH_DISCOVERY=0
WITH_CEO=0
WITH_GROWTH=0
WITH_POSITIONING=0
WITH_BUSINESS=0
WITH_OUTPUT_SAFETY=0
WITH_GATES=0
WITH_TERSE=0
WITH_OPERATING_LAYER=0
APPLY_OPLAYER=0
NO_OPLAYER=0
NO_AUTO_UPDATE=0
RECOMMEND_ONLY=0
POSITIONAL=()
TRACKER_PROJECT=""
TRACKER="linear"
POLICY=""
NEXT_OPT=""
for arg in "$@"; do
  if [[ -n "${NEXT_OPT}" ]]; then
    printf -v "${NEXT_OPT}" '%s' "${arg}"; NEXT_OPT=""; continue
  fi
  case "${arg}" in
    --tracker-project) NEXT_OPT=TRACKER_PROJECT ;;
    --tracker) NEXT_OPT=TRACKER ;;
    --policy) NEXT_OPT=POLICY ;;
    --policy=*) POLICY="${arg#*=}" ;;
    --tracker-project=*) TRACKER_PROJECT="${arg#*=}" ;;
    --tracker=*) TRACKER="${arg#*=}" ;;
    --claude-only) WRITE_AGENTS=0; MINIMAL=1 ;;
    --minimal) MINIMAL=1 ;;
    --with-codex) WITH_CODEX=1 ;;
    --with-extra-hosts) WITH_EXTRA=1 ;;
    --with-delivery) WITH_DELIVERY=1 ;;
    --with-critic) WITH_CRITIC=1 ;;
    --with-comms) WITH_COMMS=1 ;;
    --with-contribution) WITH_CONTRIBUTION=1 ;;
    --with-discovery) WITH_DISCOVERY=1 ;;
    --with-ceo) WITH_CEO=1 ;;
    --with-growth) WITH_GROWTH=1 ;;
    --with-positioning) WITH_POSITIONING=1 ;;
    --with-business) WITH_BUSINESS=1 ;;
    --with-output-safety) WITH_OUTPUT_SAFETY=1 ;;
    --with-gates) WITH_GATES=1 ;;
    --with-terse-replies) WITH_TERSE=1 ;;
    --with-operating-layer) WITH_OPERATING_LAYER=1 ;;
    --apply-operating-layer) WITH_OPERATING_LAYER=1; APPLY_OPLAYER=1 ;;
    --no-sandbox) NO_SANDBOX=1 ;;
    --no-operating-layer) NO_OPLAYER=1 ;;
    --no-auto-update) NO_AUTO_UPDATE=1 ;;
    --full) WITH_DELIVERY=1; WITH_CRITIC=1; WITH_COMMS=1 ;;
    --recommend) RECOMMEND_ONLY=1 ;;
    --with-cursor) echo "note: --with-cursor is default now; ignoring." >&2 ;;
    -p|--portable) echo "note: --portable is default; ignoring (use --minimal / --claude-only to narrow)." >&2 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown option: ${arg}" >&2; usage; exit 2 ;;
    *) POSITIONAL+=("${arg}") ;;
  esac
done

if [[ -n "${NEXT_OPT}" ]]; then echo "error: --$(printf %s "${NEXT_OPT//_/-}" | tr A-Z a-z) needs a value" >&2; exit 2; fi
# values land in AGENTS.md: allow only ID-safe characters
if [[ -n "${TRACKER_PROJECT}" && ! "${TRACKER_PROJECT}" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "error: --tracker-project must match [A-Za-z0-9._-]+" >&2; exit 2
fi
case "${TRACKER}" in linear|github|jira) ;; *) echo "error: --tracker must be linear, github or jira" >&2; exit 2 ;; esac

if [[ "${WITH_OPERATING_LAYER}" -eq 1 && "${WITH_DELIVERY}" -eq 0 ]]; then
  echo "error: --with-operating-layer requires --with-delivery (writes an agentic-delivery snippet)" >&2
  exit 1
fi

if [[ "${WITH_TERSE}" -eq 1 && "${WITH_DELIVERY}" -eq 0 ]]; then
  echo "error: --with-terse-replies requires --with-delivery (the hook script ships with agentic-delivery)" >&2
  exit 1
fi

if [[ "${NO_OPLAYER}" -eq 1 && "${WITH_OPERATING_LAYER}" -eq 1 ]]; then
  echo "error: --no-operating-layer conflicts with --with/--apply-operating-layer" >&2
  exit 1
fi

# Default-on: delivery without its operating layer installs hooks that never run (field failure).
if [[ "${WITH_DELIVERY}" -eq 1 && "${WITH_OPERATING_LAYER}" -eq 0 && "${NO_OPLAYER}" -eq 0 ]]; then
  WITH_OPERATING_LAYER=1
  if command -v jq >/dev/null 2>&1; then APPLY_OPLAYER=1
  else echo "note: jq not found; writing the operating-layer snippet to merge by hand instead of applying it" >&2; fi
fi

if [[ "${APPLY_OPLAYER}" -eq 1 ]] && ! command -v jq >/dev/null 2>&1; then
  echo "error: --apply-operating-layer needs jq (fail closed); install jq or use --with-operating-layer" >&2
  exit 1
fi

TARGET_DIR="${POSITIONAL[0]:-$(pwd)}"
POLICY_PY="${SCRIPT_DIR}/.claude/skills/agentic-delivery/scripts/perun_policy.py"

if [[ ! -d "${TARGET_DIR}" ]]; then
  echo "error: target directory does not exist: ${TARGET_DIR}" >&2
  exit 1
fi

if [[ -n "${POLICY}" ]]; then  # shape-check before touching anything; values are validated when written
  _seen=,
  IFS=, read -ra _kv <<< "${POLICY}"
  for kv in "${_kv[@]}"; do
    if [[ ! "${kv}" =~ ^([A-Za-z_]+)=(.+)$ || "${_seen}" == *",${BASH_REMATCH[1]},"* ]]; then
      echo "error: --policy wants dim=value pairs, one per dim (got '${kv}')" >&2; exit 2
    fi
    _seen="${_seen}${BASH_REMATCH[1]},"
    python3 "${POLICY_PY}" check "${kv%%=*}" "${kv#*=}" || exit 2
  done
fi

if [[ "$(cd "${TARGET_DIR}" && pwd)" == "${SCRIPT_DIR}" ]]; then
  echo "error: target is the repository itself; choose another project directory." >&2
  exit 1
fi

if [[ "${RECOMMEND_ONLY}" -eq 1 ]]; then
  exec python3 "${SCRIPT_DIR}/scripts/recommend-overlays.py" "${TARGET_DIR}"
fi

SRC_REVIEW="${SCRIPT_DIR}/.claude/skills/${REVIEW_NAME}"
if [[ ! -f "${SRC_REVIEW}/SKILL.md" ]]; then
  echo "error: cannot find ${SRC_REVIEW}/SKILL.md" >&2
  echo "Run this script from inside a cloned deep-code-review repository." >&2
  exit 1
fi

VERSION="unknown"
if [[ -f "${SRC_REVIEW}/VERSION" ]]; then
  VERSION="$(tr -d '[:space:]' < "${SRC_REVIEW}/VERSION")"
fi
INSTALL_SHA="unknown"
if git -C "${SCRIPT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  INSTALL_SHA="$(git -C "${SCRIPT_DIR}" rev-parse --short HEAD)"
fi

COMMAND_FILES=()  # files install wrote fresh (commands, house-defaults.md, settings .bak): hashed into the uninstall record
BACKUP_DIRS=()  # skill-backups dirs this run created and kept (recorded in the marker for uninstall)
install_skill_copy() {
  local skill_name="$1"
  local dest="$2"
  local backup_root="$3"
  local src="${SCRIPT_DIR}/.claude/skills/${skill_name}"
  if [[ ! -f "${src}/SKILL.md" ]]; then
    echo "error: cannot find ${src}/SKILL.md" >&2
    exit 1
  fi
  mkdir -p "$(dirname "${dest}")"
  local backup=""
  if [[ -e "${dest}" || -L "${dest}" ]]; then
    # Fail closed: a symlinked backup dir would move the user's skill (or later delete files) outside the target.
    python3 "${SCRIPT_DIR}/scripts/perun_marker.py" backup-ok "${TARGET_DIR}" "${backup_root}" \
      || { echo "error: ${backup_root} (or a parent below ${TARGET_DIR}) is a symlink; refusing to back up into it. Replace it with a real directory and re-run." >&2; exit 1; }
    mkdir -p "${backup_root}"
    # Portable, collision-free backup name: a seconds-resolution timestamp plus
    # an existence-checked numeric suffix, so rapid repeated installs within the
    # same second never reuse a name. Avoids `date +%N` (unsupported on BSD/macOS
    # date), which is why a plain timestamp alone would collide.
    backup="${backup_root}/${skill_name}-$(date +%Y%m%d-%H%M%S)"
    if [[ -e "${backup}" ]]; then
      local n=1
      while [[ -e "${backup}-${n}" ]]; do
        n=$((n + 1))
      done
      backup="${backup}-${n}"
    fi
    echo "note: existing skill found -> backing up to ${backup}"
    mv "${dest}" "${backup}"
  fi
  cp -R "${src}" "${dest}"
  # Never ship local Python bytecode caches (created by running a script selftest).
  find "${dest}" -name __pycache__ -type d -prune -exec rm -rf {} +
  # Support docs the review skill cites — must resolve after install.
  if [[ "${skill_name}" == "${REVIEW_NAME}" ]]; then
    mkdir -p "${dest}/references"
    if [[ -f "${SCRIPT_DIR}/docs/standards-index.md" ]]; then
      cp "${SCRIPT_DIR}/docs/standards-index.md" "${dest}/references/standards-index.md"
    fi
    if [[ -f "${SCRIPT_DIR}/docs/example-review-report.md" ]]; then
      cp "${SCRIPT_DIR}/docs/example-review-report.md" "${dest}/references/example-review-report.md"
    fi
  fi
  if [[ -n "${backup}" ]]; then
    # A backup byte-identical to the fresh copy is just the shipped files again: drop it so unchanged re-runs add nothing.
    # Any other backup (an edited copy, an older release, your own copy) is never deleted by install.
    python3 "${SCRIPT_DIR}/scripts/perun_marker.py" dedupe "${backup_root}" "${backup}" "${dest}"
    [[ ! -d "${backup}" ]] || BACKUP_DIRS+=("${backup#"${TARGET_DIR}"/}")
  fi
  local skill_ver="unknown"
  if [[ -f "${src}/VERSION" ]]; then
    skill_ver="$(tr -d '[:space:]' < "${src}/VERSION")"
  fi
  echo "installed: ${skill_name} ${skill_ver} (@ ${INSTALL_SHA}) -> ${dest}"
}

# Host roots that receive every selected skill.
HOSTS=()
HOSTS+=(".claude")
if [[ "${MINIMAL}" -eq 0 ]]; then
  HOSTS+=(".cursor" ".agents")
fi
if [[ "${WITH_CODEX}" -eq 1 ]]; then
  HOSTS+=(".codex")
fi
if [[ "${WITH_EXTRA}" -eq 1 ]]; then
  HOSTS+=(".gemini" ".opencode" ".github" ".windsurf" ".hermes" ".kiro" ".cline" ".roo" ".factory" ".qwen" ".grok")
fi

SKILLS=("${REVIEW_NAME}")
if [[ "${WITH_DELIVERY}" -eq 1 ]]; then
  SKILLS+=("agentic-delivery")
fi
if [[ "${WITH_CRITIC}" -eq 1 ]]; then
  SKILLS+=("idea-critic")
fi
if [[ "${WITH_COMMS}" -eq 1 ]]; then
  SKILLS+=("communication-structure")
fi
if [[ "${WITH_CONTRIBUTION}" -eq 1 ]]; then
  SKILLS+=("contribution")
fi
if [[ "${WITH_DISCOVERY}" -eq 1 ]]; then
  SKILLS+=("product-discovery")
fi
if [[ "${WITH_CEO}" -eq 1 ]]; then
  SKILLS+=("agentic-ceo")
fi
if [[ "${WITH_GROWTH}" -eq 1 ]]; then
  SKILLS+=("growth-analytics")
fi
if [[ "${WITH_POSITIONING}" -eq 1 ]]; then
  SKILLS+=("positioning")
fi
if [[ "${WITH_BUSINESS}" -eq 1 ]]; then
  SKILLS+=("business-ops")
fi
if [[ "${WITH_OUTPUT_SAFETY}" -eq 1 ]]; then
  SKILLS+=("product-output-safety")
fi

INSTALLED_DIRS=()
for skill in "${SKILLS[@]}"; do
  for host in "${HOSTS[@]}"; do
    INSTALLED_DIRS+=("${host}/skills/${skill}")
    install_skill_copy \
      "${skill}" \
      "${TARGET_DIR}/${host}/skills/${skill}" \
      "${TARGET_DIR}/${host}/skill-backups"
  done
done

# Host safety: one warning line per installed host, from the single-source table (docs/host-safety.md).
HS_TSV="${SCRIPT_DIR}/.claude/skills/agentic-delivery/templates/host-safety.tsv"
if [[ -f "${HS_TSV}" ]]; then
  for host in "${HOSTS[@]}"; do
    while IFS=$'\t' read -r hs_dir hs_name hs_sb hs_warn hs_url; do
      [[ "${hs_dir}" == "${host}" ]] && echo "safety: ${hs_name}: ${hs_warn} ${hs_url}" >&2
    done < "${HS_TSV}"
  done
fi

# write_gate_file <src> <dest> <executable:0|1> — copy a CI-gates template
# into the target. NEVER overwrites an existing file at <dest>: if one is
# already there, writes <dest>.new (or .new-N on a further collision) instead
# and prints a note so the owner reviews/merges by hand. This is the only
# writer for --with-gates output; both call sites below share it so the
# never-overwrite rule cannot drift between the workflow and the runner.
write_gate_file() {
  local src="$1" dest="$2" make_exec="$3"
  mkdir -p "$(dirname "${dest}")"
  if [[ -e "${dest}" ]]; then
    local newdest="${dest}.new"
    if [[ -e "${newdest}" ]]; then
      local n=1
      while [[ -e "${newdest}-${n}" ]]; do
        n=$((n + 1))
      done
      newdest="${newdest}-${n}"
    fi
    cp "${src}" "${newdest}"
    [[ "${make_exec}" -eq 1 ]] && chmod +x "${newdest}"
    echo "note: ${dest} already exists -> wrote ${newdest} instead (review and merge by hand)"
  else
    cp "${src}" "${dest}"
    [[ "${make_exec}" -eq 1 ]] && chmod +x "${dest}"
    echo "installed: ${dest}"
  fi
}

if [[ "${WITH_GATES}" -eq 1 ]]; then
  GATES_SRC="${SCRIPT_DIR}/.claude/skills/${REVIEW_NAME}/templates"
  if [[ ! -f "${GATES_SRC}/dcr-gates.yml" || ! -f "${GATES_SRC}/dcr-gates.sh" || ! -f "${GATES_SRC}/pre-push-verify.sh" || ! -f "${GATES_SRC}/integrator-gate.sh" ]]; then
    echo "error: cannot find ${GATES_SRC}/{dcr-gates.yml,dcr-gates.sh,pre-push-verify.sh,integrator-gate.sh}" >&2
    exit 1
  fi
  write_gate_file "${GATES_SRC}/dcr-gates.yml" "${TARGET_DIR}/.github/workflows/dcr-gates.yml" 0
  write_gate_file "${GATES_SRC}/dcr-gates.sh" "${TARGET_DIR}/scripts/dcr-gates.sh" 1
  write_gate_file "${GATES_SRC}/pre-push-verify.sh" "${TARGET_DIR}/.githooks/pre-push" 1
  write_gate_file "${GATES_SRC}/integrator-gate.sh" "${TARGET_DIR}/scripts/integrator-gate.sh" 1
  cat <<'EOF'

CI enforcement wired (--with-gates), MINIMUM-COST PROFILE by default:
  .github/workflows/dcr-gates.yml  PR-into-main ONLY (ready_for_review +
                                    synchronize; drafts skipped); no push
                                    trigger, no schedule; SHA-pinned checkout,
                                    workflow-level concurrency cancels a
                                    superseded run
  scripts/dcr-gates.sh             calls the INSTALLED skill's own gate scripts
                                    (fix_class_gate, binaries_gate) by resolved
                                    path -- no duplicated gate logic, no copies
  .githooks/pre-push               reruns the fast lint+unit tier (DCR_PREPUSH_CMD)
                                    before every push -- catches an unverified rebase-
                                    conflict-resolution commit locally, before CI. Not
                                    wired yet: run this yourself (not run by install.sh)
                                    to opt in:
                                      git config core.hooksPath .githooks
                                    Then set DCR_PREPUSH_CMD (e.g. "make lint test-unit")
                                    in your shell profile. It is self-report, not a
                                    substitute for CI -- see the hook's own header.
  scripts/integrator-gate.sh       run this on an integration branch's merge
                                    result instead of adding hosted CI to it --
                                    see its own header and
                                    agentic-delivery/references/host-enforcement.md's
                                    "Minimum-cost CI & token profile"
Edit the workflow's trigger branch if this repo's default branch isn't `main`.

MINIMUM-COST PROFILE CHECKLIST -- these are OWNER actions; install.sh never
automates them (they need forge/org privileges this script does not have):
  [ ] If this repo has a separate integration branch (development, staging,
      ...): add branch protection/ruleset restricting merge AND push to ONE
      integrator identity -- a deterministic script (never an LLM session),
      run from launchd/cron with its gate token in the OS keychain, plus a
      documented break-glass path for running it by hand. That identity runs
      `scripts/integrator-gate.sh --target-branch <branch>`, which pushes the
      merge result to a scratch ref, gates it, and only on a pass
      fast-forwards the branch -- never `[skip ci]` on that branch. Do NOT
      add hosted CI to it.
  [ ] If a required status check is needed on the integration branch: have
      integrator-gate.sh post it using a SEPARATE, low-privilege token from
      whatever pushes -- never the same identity (it would be forgeable).
  [ ] Set a soft spend budget (GitHub Settings > Billing) with alerts at
      50/80/100% of your cap -- never a hard stop that could block real CI.
  [ ] Confirm plan/ownership before relying on GitHub's merge queue: it needs
      a public repo, or a private repo owned by an org on GitHub Enterprise
      Cloud -- Team, Pro, and personal-account repos get none of it.
  [ ] Run `python3 .claude/skills/deep-code-review/scripts/ci_cost_lint.py --gate .`
      before merging any new/changed workflow file.

Optional, only useful alongside --with-delivery: --with-operating-layer WRITES the
two-tier SubagentStop hand-back cap, the SubagentStart house-default injector, and
the subagent model pin as a settings.operating-layer.json.new snippet to merge by
hand -- see agentic-delivery/references/operating-discipline.md (the always-on
operating layer's one entry point) and its "Install and self-check" section.
EOF
fi

if [[ "${WITH_TERSE}" -eq 1 ]]; then
  # Opt-in Stop hook; written as a snippet to merge by hand, never applied automatically.
  mkdir -p "${TARGET_DIR}/.claude"
  cp "${SCRIPT_DIR}/.claude/skills/agentic-delivery/templates/terse-replies.settings.json" "${TARGET_DIR}/.claude/settings.terse-replies.json.new"
  echo "  terse-replies: .claude/settings.terse-replies.json.new written -- merge its Stop hook into settings (TERSE_MAX_RATIO tunes the 0.12 limit)"
fi

if [[ "${WITH_OPERATING_LAYER}" -eq 1 ]]; then
  OPLAYER_SRC="${SCRIPT_DIR}/.claude/skills/agentic-delivery/templates/operating-layer.settings.json"
  if [[ ! -f "${OPLAYER_SRC}" ]]; then
    echo "error: cannot find ${OPLAYER_SRC}" >&2
    exit 1
  fi
  OPLAYER_JSON="$(cat "${OPLAYER_SRC}")"
  if [[ "${NO_SANDBOX}" -eq 1 ]]; then
    command -v jq >/dev/null || { echo "error: --no-sandbox needs jq (fail closed)" >&2; exit 1; }
    OPLAYER_JSON="$(jq -c 'del(.sandbox, .permissions)' "${OPLAYER_SRC}")"
    echo "warning: --no-sandbox: operating layer has NO sandbox and NO rm/sudo deny rules; an agent can delete anything you can" >&2
  fi
  OPLAYER_DEST="${TARGET_DIR}/.claude/settings.operating-layer.json.new"
  mkdir -p "$(dirname "${OPLAYER_DEST}")"
  # Default house-defaults file the SubagentStart injector reads (it fails open when absent: lanes ran uncapped). Only if absent.
  OPLAYER_HOUSE="${TARGET_DIR}/.claude/house-defaults.md"
  if [[ "${APPLY_OPLAYER}" -eq 1 && -L "${OPLAYER_HOUSE}" ]]; then
    echo "warning: ${OPLAYER_HOUSE} is a symlink; not writing a default house-defaults file (fail closed)" >&2
  elif [[ "${APPLY_OPLAYER}" -eq 1 && ! -e "${OPLAYER_HOUSE}" ]]; then
    cat > "${OPLAYER_HOUSE}" <<'HOUSE'
Lane budget: stay inside the lane token cap. Read only the line ranges you need, never re-read a file you just edited, and stop as soon as the task is done.
Optional chat voice: add your own line here; compressed assistant prose is available from the public caveman repository. Code, commits, PR bodies and docs stay normal prose.
Hand-back: one line `status | evidence (sha/path/test) | next`, at most 10 lines and 800 characters; deliverables go to files, never into chat.
HOUSE
    COMMAND_FILES+=(".claude/house-defaults.md")
    echo "wrote default ${OPLAYER_HOUSE} (edit freely; an existing file is never overwritten)"
  fi
  if [[ "${APPLY_OPLAYER}" -eq 1 ]]; then
    OPLAYER_LOCAL="${TARGET_DIR}/.claude/settings.local.json"
    [[ -f "${OPLAYER_LOCAL}" ]] || { echo '{}' > "${OPLAYER_LOCAL}"; OPLAYER_LOCAL_NEW=1; }
    OPLAYER_PRE="$(mktemp "${TMPDIR:-/tmp}/perun.XXXXXX")"; cp "${OPLAYER_LOCAL}" "${OPLAYER_PRE}"
    # Append template hook entries not already present; existing env/model win.
    # Placeholder matchers (contain "<") never fire: skip them, tell the operator.
    echo "warning: skipped template hook entries with a placeholder matcher (e.g. <your-read-only-review-type>); add a SubagentStop entry with your real review agent type by hand" >&2
    # dm: recursive merge, existing (right) values win, arrays unioned (existing order first).
    # autoCompactWindow 200000: only when no user/project/local settings file sets it (local would shadow a user's value) and policy auto_compact is not off.
    OPLAYER_AC=200000
    [[ ",${POLICY}," == *,auto_compact=off,* ]] || grep -qs '"auto_compact"[[:space:]]*:[[:space:]]*"off"' "${TARGET_DIR}/.perun/policy.json" && OPLAYER_AC=""
    for _f in "${CLAUDE_CONFIG_DIR:-${HOME}/.claude}/settings.json" "${TARGET_DIR}/.claude/settings.json" "${OPLAYER_LOCAL}"; do
      [[ -f "${_f}" ]] || continue
      if ! jq -e 'type == "object"' "${_f}" >/dev/null 2>&1; then  # invalid JSON/JSONC: cannot tell whether the user set it, so fail closed
        [[ -n "${OPLAYER_AC}" ]] && echo "note: ${_f} is not plain JSON; autoCompactWindow not written (set it there yourself)" >&2
        OPLAYER_AC=""
      elif jq -e 'has("autoCompactWindow")' "${_f}" >/dev/null 2>&1; then
        OPLAYER_AC=""
      fi
    done
    jq --argjson t "${OPLAYER_JSON}" --arg ac "${OPLAYER_AC}" '
      def dm($a; $b): if ($a|type) == "object" and ($b|type) == "object"
          then reduce ($a + $b | keys_unsorted[]) as $k ({}; .[$k] = (if ($a|has($k)) and ($b|has($k)) then dm($a[$k]; $b[$k]) elif ($b|has($k)) then $b[$k] else $a[$k] end))
        elif ($a|type) == "array" and ($b|type) == "array" then $b + ($a - $b) else $b end;
      # Upgrade old relative hook paths in place (cwd-dependent: break outside the repo root), so the union below sees no duplicate.
      def up: sub("python3 (?<p>\\.claude/skills/[A-Za-z0-9_./-]+\\.py)"; "python3 \"$CLAUDE_PROJECT_DIR/\(.p)\"")
              | sub("HOUSE_DEFAULTS_FILE=(?<p>\\.claude/[A-Za-z0-9_./-]+)"; "HOUSE_DEFAULTS_FILE=\"$CLAUDE_PROJECT_DIR/\(.p)\"");
      (.hooks[]?[]?.hooks[]? | select((.command? | type) == "string") | .command) |= up
      | reduce ($t.hooks | keys[]) as $e (.;
          (.hooks[$e] // []) as $a
          | .hooks[$e] = $a + ($t.hooks[$e] | map(select(((.matcher // "") | contains("<") | not) and (. as $x | $a | index([$x]) | not)))))
      | .env = ($t.env + (.env // {}))
      | (if $t.sandbox then .sandbox = dm($t.sandbox; .sandbox // {}) else . end)
      | (if $t.permissions then .permissions = dm($t.permissions; .permissions // {}) else . end)
      | .model //= "sonnet"
      | (if $ac != "" then .autoCompactWindow = ($ac | tonumber) else . end)' "${OPLAYER_LOCAL}" > "${OPLAYER_LOCAL}.tmp"
    if cmp -s "${OPLAYER_LOCAL}" "${OPLAYER_LOCAL}.tmp"; then
      rm -f "${OPLAYER_LOCAL}.tmp"
    else
      OPLAYER_BAK="${OPLAYER_LOCAL}.bak.$(date +%Y%m%d-%H%M%S)"   # timestamped: never overwrite an earlier backup
      OPLAYER_N=1; while [[ -e "${OPLAYER_BAK}" ]]; do OPLAYER_BAK="${OPLAYER_LOCAL}.bak.$(date +%Y%m%d-%H%M%S)-${OPLAYER_N}"; OPLAYER_N=$((OPLAYER_N + 1)); done
      cp "${OPLAYER_LOCAL}" "${OPLAYER_BAK}"
      COMMAND_FILES+=("${OPLAYER_BAK#"${TARGET_DIR}"/}")
      mv "${OPLAYER_LOCAL}.tmp" "${OPLAYER_LOCAL}"
    fi
    OPLAYER_AGENT="${TARGET_DIR}/.claude/agents/delivery-lane.md"
    if [[ ! -e "${OPLAYER_AGENT}" ]]; then
      OPLAYER_AGENT_NEW=1
      mkdir -p "$(dirname "${OPLAYER_AGENT}")"
      cat > "${OPLAYER_AGENT}" <<'AGENT'
---
name: delivery-lane
description: Default delivery lane for bounded implementation work. Terse, cheap, one-line hand-back.
model: sonnet
---
Do the assigned bounded task with the simplest change that works. Read only the line ranges you need. Run the project's own gates before claiming done. Final message is one line: status, evidence (sha/path/test), next step.
AGENT
    fi
    echo "applied operating layer to ${OPLAYER_LOCAL} (backup: .bak.<timestamp> if changed); verify with:"
    if [[ "${NO_SANDBOX}" -eq 0 ]]; then
      echo "  what changed (sandbox): sandbox.enabled=true, sandbox.allowUnsandboxedCommands=false, autonomy-ready defaults (gh excluded with read-only gh subcommands allowed, common dev hosts, local binding, ~/.cache and ~/.npm writes; existing values win, lists unioned), deny Bash(rm -rf *), Bash(rm -fr *), Bash(rm -r *), Bash(rm -R *), Bash(sudo *) and gh alias/extension/repo delete/release delete; opt out with --no-sandbox"
      echo "  why each default: docs/host-safety.md#autonomy-ready-defaults"
      echo "  sandbox blocks gh (x509 -26276) or a dev server (EPERM)? see docs/host-safety.md#common-sandbox-errors"
    fi
    echo "  python3 .claude/skills/agentic-delivery/scripts/operating_selfcheck.py --settings .claude/settings.local.json"
  else
  if [[ -e "${OPLAYER_DEST}" ]]; then
    OPLAYER_N=1
    while [[ -e "${OPLAYER_DEST}-${OPLAYER_N}" ]]; do
      OPLAYER_N=$((OPLAYER_N + 1))
    done
    OPLAYER_DEST="${OPLAYER_DEST}-${OPLAYER_N}"
  fi
  printf '%s\n' "${OPLAYER_JSON}" > "${OPLAYER_DEST}"
  echo "wrote ${OPLAYER_DEST} -- merge its \"hooks\"/\"env\" keys into ${TARGET_DIR}/.claude/settings.json by hand, then verify with:"
  echo "  python3 .claude/skills/agentic-delivery/scripts/operating_selfcheck.py"
  fi
fi

# Slash commands: copy commands/*.md into .claude/commands/, but only those whose skill is installed.
# review, deliver always; cost-retro, perun, perun-run need agentic-ceo/agentic-delivery.
# Never overwrites (write_gate_file writes <dest>.new); only files written fresh go in the uninstall record.
if [[ -d "${SCRIPT_DIR}/commands" ]]; then
  for cmd in "${SCRIPT_DIR}"/commands/*.md; do
    name="$(basename "${cmd}" .md)"
    case "${name}" in
      review|deliver) ;;
      cost-retro|perun|perun-run) [[ "${WITH_CEO}" -eq 1 || "${WITH_DELIVERY}" -eq 1 ]] || continue ;;
      *) continue ;;
    esac
    dest="${TARGET_DIR}/.claude/commands/${name}.md"
    [[ -e "${dest}" ]] && cmp -s "${cmd}" "${dest}" && continue  # re-install: already current
    existed=0; [[ -e "${dest}" ]] && existed=1
    write_gate_file "${cmd}" "${dest}" 0
    [[ "${existed}" -eq 1 ]] || COMMAND_FILES+=(".claude/commands/${name}.md")
  done
fi

# Marker: exactly what this install added, so perun_uninstall.py removes only that.
# Remote: PERUN_REMOTE, else this checkout's origin, else (tarball/plugin copy with no git origin) the canonical public repo, so auto-update always has one.
RECORD_REMOTE="${PERUN_REMOTE:-$(git -C "${SCRIPT_DIR}" remote get-url origin 2>/dev/null | sed -E 's#://[^/@]+@#://#' || true)}"
python3 "${SCRIPT_DIR}/scripts/perun_marker.py" "${TARGET_DIR}" --dirs "${INSTALLED_DIRS[@]}" ${COMMAND_FILES[@]+--files "${COMMAND_FILES[@]}"} \
  ${BACKUP_DIRS[@]+--backups "${BACKUP_DIRS[@]}"} ${OPLAYER_LOCAL_NEW:+--settings-created} \
  ${OPLAYER_PRE:+--pre "${OPLAYER_PRE}" --template "${SCRIPT_DIR}/.claude/skills/agentic-delivery/templates/operating-layer.settings.json"} \
  ${OPLAYER_AGENT_NEW:+--agent-created} --version "${VERSION}" \
  --remote "${RECORD_REMOTE:-https://github.com/protocol/perun.git}"
if [[ "${NO_AUTO_UPDATE}" -eq 1 ]]; then
  python3 - "${TARGET_DIR}/.perun/policy.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
pol = json.loads(p.read_text()) if p.is_file() else {}
pol["auto_update"] = "off"
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(pol, indent=2) + "\n")
PY
  echo "auto-update: off (${TARGET_DIR}/.perun/policy.json)"
fi
if [[ "${WITH_OPERATING_LAYER}" -eq 1 && "${APPLY_OPLAYER}" -eq 1 ]]; then
  OPLAYER_MODEL_NOTE="(model: sonnet, set only if you had none)"
  if [[ -n "${OPLAYER_PRE:-}" ]] && jq -e 'has("model")' "${OPLAYER_PRE}" >/dev/null 2>&1; then
    OPLAYER_MODEL_NOTE="(your existing model kept)"
  fi
  cat <<EOF

What changed in ${TARGET_DIR}:
  1. Skills copied to .claude/skills (+ .cursor, .agents); any existing copy moved to <host>/skill-backups/.
  2. .claude/settings.local.json: operating-layer hooks (PreToolUse incl. heavy_gate.py + lane_resume_nudge.py + ceo_altitude_guard.py, PostToolUse lane_cap.py, SessionStart session_brief.py + handoff_inject.py + auto-update, UserPromptSubmit context_nudge.py + auto-update + ceo_altitude_guard.py, SubagentStart, SubagentStop), env (incl. LANE_TOOL_CAP=250), the model pin ${OPLAYER_MODEL_NOTE} and autoCompactWindow=200000 (only if no settings file sets it; policy auto_compact=off skips) merged in; previous file saved as .bak.<timestamp>.
     Skills and permissions apply to open sessions without a restart; a hook change (new entries, or old relative paths upgraded to "\$CLAUDE_PROJECT_DIR" paths) and a model change reach already-running sessions only after a restart.
     Auto-update: that hook runs release code from the Perun remote in the background (newest vX.Y.Z tag, at most every 6h).
     Opt out: re-run install.sh with --no-auto-update, or set "auto_update": "off" in .perun/policy.json.
  3. .claude/agents/delivery-lane.md added if absent; .claude/.perun-install.json and .dcr-install-flags record what was added.
  4. Check it works: python3 ${SCRIPT_DIR}/scripts/perun_doctor.py ${TARGET_DIR}
  5. Undo: python3 ${SCRIPT_DIR}/scripts/perun_uninstall.py ${TARGET_DIR}   (opt out next time: --no-operating-layer)
EOF
fi

[[ -z "${OPLAYER_PRE:-}" ]] || rm -f "${OPLAYER_PRE}"

# Record the flags so scripts/update-installed.sh can replay this install. Flags that add capability or reduce
# safety (operating layer on, sandbox off) are machine-local and go to an untracked .dcr-install-flags.local so a committed record
# never replays one person's choice on another clone. Pack flags and the conservative opt-outs
# (--no-auto-update, --no-operating-layer) stay tracked so a team-wide opt-out travels.
mkdir -p "${TARGET_DIR}/.claude"
LOCAL_FLAGS="${TARGET_DIR}/.claude/.dcr-install-flags.local"
{ skip=0
  for a in "$@"; do
    if [[ "${skip}" -eq 1 ]]; then skip=0; continue; fi
    case "${a}" in --tracker-project|--tracker|--tracker-project=*|--tracker=*) [[ "${a}" == *=* ]] || skip=1; continue ;; esac
    case "${a}" in --with-operating-layer|--apply-operating-layer|--no-sandbox) continue ;; esac
    [[ "${a}" == -* ]] && printf '%s\n' "${a}"
  done
  # tracker flags replay as single-token --opt=value lines (the marker is one arg per line)
  [[ -n "${TRACKER_PROJECT}" ]] && printf -- '--tracker-project=%s\n--tracker=%s\n' "${TRACKER_PROJECT}" "${TRACKER}"
  true; } > "${TARGET_DIR}/.claude/.dcr-install-flags"
for a in "$@"; do
  case "${a}" in --with-operating-layer|--apply-operating-layer|--no-sandbox) printf '%s\n' "${a}" ;; esac
done > "${LOCAL_FLAGS}"
if [[ -s "${LOCAL_FLAGS}" ]]; then  # keep the local record out of git without touching a tracked .gitignore
  _ex="$(git -C "${TARGET_DIR}" rev-parse --git-path info/exclude 2>/dev/null || true)"
  [[ -z "${_ex}" || "${_ex}" == /* ]] || _ex="${TARGET_DIR}/${_ex}"
  _pat="/$(git -C "${TARGET_DIR}" rev-parse --show-prefix 2>/dev/null || true).claude/.dcr-install-flags.local"
  if [[ -n "${_ex}" ]] && ! grep -qxF "${_pat}" "${_ex}" 2>/dev/null; then
    { mkdir -p "$(dirname "${_ex}")" && printf '%s\n' "${_pat}" >> "${_ex}"; } 2>/dev/null || true
  fi
else
  rm -f "${LOCAL_FLAGS}"
fi
# session_brief.py compares the installed version to this checkout's origin/main (machine-local, never committed).
if [[ "${APPLY_OPLAYER}" -eq 1 ]]; then
  { mkdir -p "${XDG_CACHE_HOME:-${HOME}/.cache}/perun" && printf '%s\n' "${SCRIPT_DIR}" > "${XDG_CACHE_HOME:-${HOME}/.cache}/perun/source"; } 2>/dev/null || true
fi

AGENTS_BLOCKS=(); AGENTS_CREATED=""
upsert_agents_block() {
  local agents="$1"
  local marker_begin="$2"
  local marker_end="$3"
  local block="$4"
  AGENTS_BLOCKS+=("${marker_begin%:begin}")
  if [[ -f "${agents}" ]] && grep -q "${marker_begin}" "${agents}"; then
    local block_file out_file
    block_file="$(mktemp "${TMPDIR:-/tmp}/perun.XXXXXX")"
    out_file="$(mktemp "${TMPDIR:-/tmp}/perun.XXXXXX")"
    printf '%s\n' "${block}" > "${block_file}"
    # awk-v-ok: markers and a file path, single-line by construction
    awk -v begin="<!-- ${marker_begin} -->" -v end="<!-- ${marker_end} -->" \
      -v bf="${block_file}" '
      BEGIN {
        while ((getline line < bf) > 0) { newblock = newblock line ORS }
        close(bf)
      }
      $0 == begin { printf "%s", newblock; skip=1; next }
      skip && $0 == end { skip=0; next }
      !skip { print }
    ' "${agents}" > "${out_file}"
    mv "${out_file}" "${agents}"
    rm -f "${block_file}"
    echo "agents: refreshed ${marker_begin} (v${VERSION} @ ${INSTALL_SHA}) -> ${agents}"
  elif [[ -f "${agents}" ]]; then
    printf '\n%s\n' "${block}" >> "${agents}"
    echo "agents: appended ${marker_begin} -> ${agents}"
  else
    printf '# AGENTS.md\n\n%s\n' "${block}" > "${agents}"
    AGENTS_CREATED=1
    echo "agents: created ${agents} with ${marker_begin}"
  fi
}

if [[ "${WRITE_AGENTS}" -eq 1 ]]; then
  AGENTS="${TARGET_DIR}/AGENTS.md"
  LOCATIONS=""
  if [[ "${MINIMAL}" -eq 0 ]]; then
    LOCATIONS="also .cursor/skills/ and .agents/skills/"
  fi
  if [[ "${WITH_CODEX}" -eq 1 ]]; then
    LOCATIONS="${LOCATIONS:+${LOCATIONS}; }.codex/skills/"
  fi
  if [[ "${WITH_EXTRA}" -eq 1 ]]; then
    LOCATIONS="${LOCATIONS:+${LOCATIONS}; }extra hosts (.gemini .opencode .github .windsurf .hermes .kiro .cline .roo .factory .qwen .grok)"
  fi
  # Primary path is stated once; the parenthetical lists only the MIRROR roots
  # (empty under --minimal, so no bare "()" and no path repeated).
  if [[ -n "${LOCATIONS}" ]]; then
    PRIMARY_PATH_LINE="Primary path: \`.claude/skills/${REVIEW_NAME}/SKILL.md\` (${LOCATIONS})."
  else
    PRIMARY_PATH_LINE="Primary path: \`.claude/skills/${REVIEW_NAME}/SKILL.md\`."
  fi
  REVIEW_BLOCK="$(cat <<EOF
<!-- deep-code-review:begin -->
## Code review — deep-code-review
Installed: **${VERSION}** (@ \`${INSTALL_SHA}\`). Agent-agnostic method.
${PRIMARY_PATH_LINE} Scope: \`FULL\` | \`DIFF <base-ref>\` | \`FILE <paths>\`; or say it in plain words, e.g. "run a deep code review FILE app.py" (\`/deep-code-review <scope>\` only where the host has slash commands).
Re-run upstream \`install.sh\` to refresh.
<!-- deep-code-review:end -->
EOF
)"
  upsert_agents_block "${AGENTS}" "deep-code-review:begin" "deep-code-review:end" "${REVIEW_BLOCK}"

  if [[ "${WITH_DELIVERY}" -eq 1 || "${WITH_CRITIC}" -eq 1 || "${WITH_COMMS}" -eq 1 || "${WITH_CONTRIBUTION}" -eq 1 || "${WITH_DISCOVERY}" -eq 1 || "${WITH_CEO}" -eq 1 || "${WITH_GROWTH}" -eq 1 || "${WITH_POSITIONING}" -eq 1 || "${WITH_BUSINESS}" -eq 1 || "${WITH_OUTPUT_SAFETY}" -eq 1 ]]; then
    OVERLAY_LINES=""
    if [[ "${WITH_DELIVERY}" -eq 1 ]]; then
      OVERLAY_LINES="${OVERLAY_LINES} \`agentic-delivery\`"
    fi
    if [[ "${WITH_CRITIC}" -eq 1 ]]; then
      OVERLAY_LINES="${OVERLAY_LINES} \`idea-critic\`"
    fi
    if [[ "${WITH_COMMS}" -eq 1 ]]; then
      OVERLAY_LINES="${OVERLAY_LINES} \`communication-structure\`"
    fi
    if [[ "${WITH_CONTRIBUTION}" -eq 1 ]]; then
      OVERLAY_LINES="${OVERLAY_LINES} \`contribution\`"
    fi
    if [[ "${WITH_DISCOVERY}" -eq 1 ]]; then
      OVERLAY_LINES="${OVERLAY_LINES} \`product-discovery\`"
    fi
    if [[ "${WITH_CEO}" -eq 1 ]]; then
      OVERLAY_LINES="${OVERLAY_LINES} \`agentic-ceo\`"
    fi
    if [[ "${WITH_GROWTH}" -eq 1 ]]; then
      OVERLAY_LINES="${OVERLAY_LINES} \`growth-analytics\`"
    fi
    if [[ "${WITH_POSITIONING}" -eq 1 ]]; then
      OVERLAY_LINES="${OVERLAY_LINES} \`positioning\`"
    fi
    if [[ "${WITH_BUSINESS}" -eq 1 ]]; then
      OVERLAY_LINES="${OVERLAY_LINES} \`business-ops\`"
    fi
    if [[ "${WITH_OUTPUT_SAFETY}" -eq 1 ]]; then
      OVERLAY_LINES="${OVERLAY_LINES} \`product-output-safety\`"
    fi
    OVERLAY_BLOCK="$(cat <<EOF
<!-- dcr-overlays:begin -->
## Optional overlays (deep-code-review ${VERSION} @ \`${INSTALL_SHA}\`)
Installed, each at \`.claude/skills/<name>/SKILL.md\`:${OVERLAY_LINES}. Persisted artifacts stay normal English.
Re-run upstream \`install.sh\` with the same \`--with-*\` flags (or \`--full\`) to refresh.
<!-- dcr-overlays:end -->
EOF
)"
    upsert_agents_block "${AGENTS}" "dcr-overlays:begin" "dcr-overlays:end" "${OVERLAY_BLOCK}"
  fi
  if [[ -n "${TRACKER_PROJECT}" ]]; then
    TRACKER_BLOCK="$(cat <<EOF
<!-- dcr-tracker:begin -->
## Work tracking (${TRACKER}, project \`${TRACKER_PROJECT}\`)
Every deliverable is a ${TRACKER} issue in this project; chores are PR checklist lines, not issues.
- Status moves: In Progress at start, In Review at PR open, Done only after the merge is confirmed.
- Put the issue ID in the title of only the PR that completes it. Slices, reverts, partial work and merge-train
  members use \`Refs ID\` in the body, so the integration does not auto-close the issue.
- Write \`repo PR 123\`, never \`#123\`, in tracker text (it autolinks to a guessed repo).
- Set issue priority; leave project priority to its portfolio owner. Dependencies are blocks/blocked-by relations.
- Weekly: draft the update with \`tracker_weekly_update.py\`; hygiene: \`tracker_check.py\` (agentic-delivery scripts).
Details: \`.claude/skills/agentic-delivery/references/work-tracking.md\` (needs \`--with-delivery\`).
<!-- dcr-tracker:end -->
EOF
)"
    upsert_agents_block "${AGENTS}" "dcr-tracker:begin" "dcr-tracker:end" "${TRACKER_BLOCK}"
  fi
  python3 "${SCRIPT_DIR}/scripts/perun_marker.py" "${TARGET_DIR}" --agents-block "${AGENTS_BLOCKS[@]}" ${AGENTS_CREATED:+--agents-created}
  echo "  works with Cursor, Claude Code, Codex, Copilot, Gemini, Aider, Windsurf, OpenCode, Hermes, Kiro, ..."
fi

echo "run it:  tell your agent in plain words: run a deep code review FILE <a file in your project>"
echo "  (/deep-code-review <scope> also works on hosts with slash commands, e.g. Claude Code)"
echo "  scopes: FULL | DIFF <base-ref> | FILE <paths>"
echo "  read:   .claude/skills/${REVIEW_NAME}/SKILL.md (mirrors under other hosts when installed)"
if [[ "${WITH_DELIVERY}" -eq 1 ]]; then
  echo "  delivery: load agentic-delivery for gated multi-role work"
fi
if [[ "${WITH_CRITIC}" -eq 1 ]]; then
  echo "  critic:   load idea-critic before a plan reaches the owner"
fi
if [[ "${WITH_COMMS}" -eq 1 ]]; then
  echo "  comms:    load communication-structure before any human-facing message"
fi
if [[ "${WITH_GATES}" -eq 1 ]]; then
  echo "  gates:    dcr-gates.yml + scripts/dcr-gates.sh wired -- push/open a PR to run them"
fi
if [[ "${WITH_OPERATING_LAYER}" -eq 1 ]]; then
  [[ "${APPLY_OPLAYER}" -eq 1 ]] && echo "  operating-layer: applied to .claude/settings.local.json" || echo "  operating-layer: settings.operating-layer.json.new written -- merge it, then run operating_selfcheck.py"
fi

# First-run sandbox probe: harmless checks, one-line verdict, never fails the install.
PROBE="${SCRIPT_DIR}/.claude/skills/agentic-delivery/scripts/sandbox_probe.py"
if [[ -z "${DCR_NO_PROBE:-}" && -f "${PROBE}" ]] && command -v python3 >/dev/null; then
  python3 "${PROBE}" --verdict-only "${TARGET_DIR}" 2>/dev/null || true
fi

# Autonomy advice: read-only; prints the "To run autonomously, add:" section (what this repo's own flows need
# granted, least privilege). Never writes a settings file; never fails the install.
PREFLIGHT="${SCRIPT_DIR}/.claude/skills/agentic-delivery/scripts/sandbox_preflight.py"
if [[ -f "${PREFLIGHT}" ]] && command -v python3 >/dev/null; then
  echo
  python3 "${PREFLIGHT}" "${TARGET_DIR}" 2>/dev/null || true
  echo
fi

# Policy file pinned to the target: never $PERUN_POLICY, never a parent dir's file.
PERUN_POLICY_FILE="$(cd "${TARGET_DIR}" && pwd)/.perun/policy.json"
if [[ -n "${POLICY}" ]]; then
  for kv in "${_kv[@]}"; do
    PERUN_POLICY="${PERUN_POLICY_FILE}" python3 "${POLICY_PY}" set "${kv%%=*}" "${kv#*=}" >/dev/null || exit 2
  done
fi
if [[ -f "${PERUN_POLICY_FILE}" ]]; then POLICY_LINE="$(PERUN_POLICY="${PERUN_POLICY_FILE}" python3 "${POLICY_PY}" show)" || exit 2
else POLICY_LINE="defaults (no .perun/policy.json)"; fi

# Last three lines, plain English: what changed, the one next command, how to undo.
echo "Policy: ${POLICY_LINE}"
echo
echo "Perun installed ${#SKILLS[@]} skill(s) into ${#HOSTS[@]} tool folder(s) of ${TARGET_DIR}."
echo "Next, run this one command to confirm it works: python3 ${SCRIPT_DIR}/scripts/perun_doctor.py ${TARGET_DIR}"
echo "To undo everything this install added: python3 ${SCRIPT_DIR}/scripts/perun_uninstall.py ${TARGET_DIR}"
