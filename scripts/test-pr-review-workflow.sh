#!/usr/bin/env bash
# Tests for templates/perun-review.yml: parses, passes actionlint when installed, trigger and permission
# assertions (least privilege, no pull_request_target, secret only in the read-only job), and that
# install.sh never ships or enables it. Prints PASS/FAIL lines; exits non-zero on any failure.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WF="$ROOT/.claude/skills/deep-code-review/templates/perun-review.yml"
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

[ -f "$WF" ]; ok $? "template exists"

if command -v actionlint >/dev/null 2>&1; then
  actionlint "$WF"; ok $? "actionlint clean"
elif [ -n "${REQUIRE_ACTIONLINT:-}" ]; then
  echo "FAIL  actionlint required (REQUIRE_ACTIONLINT) but not installed"; fail=$((fail + 1))
else
  echo "SKIP  actionlint not installed"
fi

python3 - "$WF" <<'PY'
import sys, yaml
w = yaml.safe_load(open(sys.argv[1]))
on = w.get(True, w.get("on"))          # YAML 1.1 parses bare `on` as True
jobs = w["jobs"]
def step_of(job, key): return next(s for s in job["steps"] if key in s.get("name", ""))
def run_of(job, key): return step_of(job, key)["run"]
checks = [
    ("trigger is only pull_request", set(on) == {"pull_request"}),
    ("top-level permissions empty", w["permissions"] == {}),
    ("review job: contents read only", jobs["review"]["permissions"] == {"contents": "read"}),
    ("post job: pull-requests+checks write, contents read",
     jobs["post"]["permissions"] == {"contents": "read", "pull-requests": "write", "checks": "write"}),
    ("review skips fork PRs", "head.repo.full_name == github.repository" in jobs["review"]["if"]),
    ("post depends on review", jobs["post"]["needs"] == "review"),
    ("jobs have timeouts", all("timeout-minutes" in j for j in jobs.values())),
    ("spend cap env present and passed to CLI",
     "DCR_MAX_BUDGET_USD" in w["env"] and "--max-budget-usd" in str(jobs["review"])),
    ("review tools are read-only", '--allowedTools "Read,Grep,Glob"' in run_of(jobs["review"], "headless")),
    ("review denies shell/edit/web and ignores project settings",
     all(x in run_of(jobs["review"], "headless") for x in ('--disallowedTools "Bash,Write,Edit,WebFetch,WebSearch"', "--setting-sources user"))),
    ("spend cap flag is in the claude step run text", "--max-budget-usd" in run_of(jobs["review"], "headless")),
    ("review checks out PR head with full history and diffs it",
     jobs["review"]["steps"][0]["with"].get("fetch-depth") == 0 and "head.sha" in str(jobs["review"]["steps"][0]["with"])
     and "git diff" in run_of(jobs["review"], "Install")),
    ("CLI install is a separate, pinned, secret-free step",
     "ANTHROPIC_API_KEY" not in str(step_of(jobs["review"], "Install").get("env")) and "@$CLAUDE_CODE_VERSION" in run_of(jobs["review"], "Install")
     and "PIN_ME" in w["env"]["CLAUDE_CODE_VERSION"]),
    ("review validates every finding row", "malformed finding row" in run_of(jobs["review"], "headless")),
    ("post sanitizes severity and pins commit to head", all(x in run_of(jobs["post"], "Ground") for x in ('"red", "yellow", "green"', 'os.environ["HEAD_SHA"]'))),
    ("post validates (dry run) before deleting the old review",
     run_of(jobs["post"], "Ground").index("findings.json >/dev/null") < run_of(jobs["post"], "Ground").index("-X DELETE")),
    ("post checks out base sha, not head",
     "base.sha" in str(jobs["post"]["steps"][0]) and "head.sha" not in str(jobs["post"]["steps"][0].get("with"))),
    ("model secret only in review job", "secrets." not in str(jobs["post"]) and "ANTHROPIC_API_KEY" in str(jobs["review"])),
    ("post posts via post_review.sh --post", "post_review.sh" in str(jobs["post"]) and "--post" in str(jobs["post"])),
    ("no PR text interpolated in run lines",
     not any("github.event.pull_request.title" in s.get("run", "") or "github.event.pull_request.body" in s.get("run", "")
             or "${{" in s.get("run", "") for j in jobs.values() for s in j["steps"])),
    ("persist-credentials false on every checkout",
     all(s.get("with", {}).get("persist-credentials") is False
         for j in jobs.values() for s in j["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))),
]
bad = 0
for name, good in checks:
    print(("PASS  " if good else "FAIL  ") + name)
    bad += not good
sys.exit(bad)
PY
rc=$?; [ "$rc" -eq 0 ] && pass=$((pass + 1)) || fail=$((fail + rc))
echo "(python assertion block rc=$rc)"

! grep -q "perun-review" "$ROOT/install.sh"; ok $? "install.sh never references the template (opt-in)"
! grep -q "pull_request_target" <(grep -v '^ *#' "$WF"); ok $? "no pull_request_target outside comments"

# the cleanup filter prefix in the workflow must match the body prefix post_review.sh writes
pfx=$(sed -n 's/.*startswith("\(Review findings (draft\)").*/\1/p' "$WF" | head -n1)
[ -n "$pfx" ] && grep -qF "\"$pfx" "$ROOT/.claude/skills/deep-code-review/scripts/post_review.sh"; ok $? "cleanup prefix matches post_review.sh body"

# grounding step must not be a dead reference to a missing script
! grep -q "finding_ground_check" "$WF"; ok $? "no reference to a nonexistent grounding script"

# the counts snippet runs on a sample findings.json
sed -n '/counts=\$(python3/,/^ *PY$/p' "$WF" | sed '1d;$d' | sed 's/^          //' > "${TMPDIR:-/tmp}/perun-counts.$$.py"
printf '{"findings":[{"severity":"red","polarity":"gap"},{"severity":"red"},{"severity":"green","polarity":"strength"}]}' > "${TMPDIR:-/tmp}/perun-f.$$.json"
out=$(cd "${TMPDIR:-/tmp}" && cp perun-f.$$.json findings.json && python3 perun-counts.$$.py); [ "$out" = "red: 2" ]; ok $? "counts snippet output on sample"
rm -f "${TMPDIR:-/tmp}"/perun-counts.$$.py "${TMPDIR:-/tmp}"/perun-f.$$.json "${TMPDIR:-/tmp}/findings.json"

# install.sh --with-gates must not drop the template into a target repo
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-prw.XXXXXX"); trap '[ -n "$T" ] && rm -rf "$T"' EXIT; git -C "$T" init -q; bash "$ROOT/install.sh" --with-gates "$T" >/dev/null 2>&1
[ ! -e "$T/.github/workflows/perun-review.yml" ]; ok $? "install --with-gates does not install perun-review.yml"

echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
