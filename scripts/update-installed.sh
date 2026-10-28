#!/usr/bin/env bash
# Re-run install.sh on each TARGET with the flags recorded by its last install
# (TARGET/.claude/.dcr-install-flags plus the untracked .dcr-install-flags.local, the only place --apply/--with-operating-layer and --no-sandbox are honored), so installed skills track this checkout.
# First fetches this checkout and fast-forwards it when behind its upstream;
# refuses on a dirty tree, diverged history, or no upstream (DCR_NO_PULL=1 skips).
# Usage: scripts/update-installed.sh TARGET...
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ $# -gt 0 ]] || { echo "usage: $0 TARGET..." >&2; exit 2; }
if [[ "${DCR_NO_PULL:-0}" != 1 ]]; then
  git -C "${HERE}" fetch -q || { echo "error: git fetch failed in ${HERE}" >&2; exit 1; }
  git -C "${HERE}" rev-parse -q --verify '@{u}' >/dev/null \
    || { echo "error: ${HERE} has no upstream branch; set one or use DCR_NO_PULL=1" >&2; exit 1; }
  if [[ "$(git -C "${HERE}" rev-parse HEAD)" != "$(git -C "${HERE}" rev-parse '@{u}')" ]]; then
    [[ -z "$(git -C "${HERE}" status --porcelain --untracked-files=no)" ]] \
      || { echo "error: ${HERE} has uncommitted changes; commit or stash, then retry" >&2; exit 1; }
    git -C "${HERE}" pull -q --ff-only \
      || { echo "error: ${HERE} cannot fast-forward (diverged from upstream); resolve manually" >&2; exit 1; }
  fi
fi
echo "dcr version: $(cat "${HERE}/.claude/skills/deep-code-review/VERSION")"
# One bad target must not abort the rest: run each in a function (|| disables set -e, so return explicitly).
update_one() {
  local t="$1" m inf p l flags mf _kept
  m="${t}/.claude/.dcr-install-flags"
  mf="${m}.local"
  if [[ ! -f "${m}" ]]; then
    # Pre-marker install: infer one flag per installed sibling skill, plus the operating layer.
    inf=()
    for p in agentic-delivery:--with-delivery idea-critic:--with-critic communication-structure:--with-comms \
      contribution:--with-contribution product-discovery:--with-discovery agentic-ceo:--with-ceo \
      growth-analytics:--with-growth positioning:--with-positioning business-ops:--with-business \
      product-output-safety:--with-output-safety; do
      [[ -d "${t}/.claude/skills/${p%%:*}" ]] && inf+=("${p#*:}")
    done
    [[ -d "${t}/.claude/skills/deep-code-review" ]] \
      || { echo "error: no install marker at ${m} and no deep-code-review skill to infer from; run install.sh once first" >&2; return 1; }
    mkdir -p "${t}/.claude" || return 1
    if [[ ! -f "${mf}" ]] && grep -qs subagent_start_inject.py "${t}/.claude/settings.local.json"; then
      printf '%s\n' --apply-operating-layer > "${mf}" || return 1
    fi
    printf '%s\n' ${inf[@]+"${inf[@]}"} > "${m}" || return 1
    echo "no install marker in ${t}; inferred flags: ${inf[*]:-(none, review-only)}; wrote ${m}"
  fi
  flags=()
  while IFS= read -r l; do [[ -n "${l}" ]] && flags+=("${l}"); done < "${m}"
  # the tracked record may not carry capability-adding / safety-reducing flags: ignore + warn (they are local-only)
  for l in "${flags[@]+"${flags[@]}"}"; do
    case "${l}" in --apply-operating-layer|--with-operating-layer|--no-sandbox)
      echo "warning: ignoring ${l} in tracked ${m} (machine-local only); re-run install.sh with ${l} on this machine to keep it" >&2 ;;
    esac
  done
  _kept=(); for l in ${flags[@]+"${flags[@]}"}; do
    case "${l}" in --apply-operating-layer|--with-operating-layer|--no-sandbox) ;; *) _kept+=("${l}") ;; esac
  done; flags=(${_kept[@]+"${_kept[@]}"})
  # machine-local flags (untracked): the only place the three local-only flags are honored
  if [[ -f "${mf}" ]]; then while IFS= read -r l; do [[ -n "${l}" ]] && flags+=("${l}"); done < "${mf}"; fi
  bash "${HERE}/install.sh" ${flags[@]+"${flags[@]}"} "${t}" || return 1
  # drift report (warn only: install keeps user-edited files by design): vendored skill files that differ from this source
  python3 "${HERE}/.claude/skills/agentic-delivery/scripts/vendor_drift.py" "${t}" --src "${HERE}/.claude/skills" >&2 || echo "warning: ${t}: vendored skills drift from canonical (see above)" >&2
}
failed=()
for t in "$@"; do update_one "$t" || failed+=("$t"); done
[[ ${#failed[@]} -eq 0 ]] || { echo "error: failed targets: ${failed[*]}" >&2; exit 1; }
