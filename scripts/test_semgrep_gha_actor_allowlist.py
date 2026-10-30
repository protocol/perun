#!/usr/bin/env python3
"""Tests for the bundled semgrep rule perun.gha.actor-allowlist-from-vars (templates/semgrep-taint/gha.yml).

Fixtures are annotated like semgrep's own tests: a `# ruleid: <id>` comment marks the NEXT line as a required finding, a
`# ok: <id>` comment marks the next line as one that must stay clean, and every unannotated line must stay clean too (so
must a copy of the workflow text outside the scanned paths). All names, users and values are fictional. RULES=<file|dir>
checks another copy of the rules (used to show the cases fail without gha.yml). The live check needs semgrep (run offline,
one job) and prints SKIP without it (CI installs none); the offline checks replay the rule's own regexes with Python's re
and always run. Plain asserts."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
RID = "perun.gha.actor-allowlist-from-vars"

# Every positive is one actor check fed by vars.NAME; the name-hint cases (the allow-list is read into a variable, then the
# actor is compared in the script) pair a hint-named variable and an actor reference in ONE step, in either order.
RELEASE = r'''name: release
on: workflow_dispatch
jobs:
  list-in-job-if:
    runs-on: ubuntu-latest
    # ruleid: perun.gha.actor-allowlist-from-vars
    if: contains(fromJSON(vars.RELEASERS), github.actor)
    steps:
      - run: ./publish.sh
  equals-any-name:
    runs-on: ubuntu-latest
    # ruleid: perun.gha.actor-allowlist-from-vars
    if: ${{ github.actor == vars.RELEASE_MANAGER }}
    steps:
      - run: ./publish.sh
  variable-first:
    runs-on: ubuntu-latest
    # ruleid: perun.gha.actor-allowlist-from-vars
    if: vars.PUBLISH_OWNER != github.triggering_actor
    steps:
      - run: ./publish.sh
  contains-any-name:
    runs-on: ubuntu-latest
    # ruleid: perun.gha.actor-allowlist-from-vars
    if: contains(vars.PUBLISH_USERS, github.actor)
    steps:
      - run: ./publish.sh
  steps:
    runs-on: ubuntu-latest
    steps:
      # ruleid: perun.gha.actor-allowlist-from-vars
      - if: contains(vars.DEPLOY_ALLOWLIST, github.triggering_actor)
        run: ./publish.sh
      - name: shell, one line
        run: |
          # ruleid: perun.gha.actor-allowlist-from-vars
          echo "${{ vars.RELEASERS }}" | tr ',' '\n' | grep -qx "${{ github.actor }}"
      - name: list in env, actor in the script
        env:
          # ruleid: perun.gha.actor-allowlist-from-vars
          ALLOWED: ${{ vars.ALLOWED_USERS }}
        run: |
          case ",$ALLOWED," in *",$GITHUB_ACTOR,"*) ;; *) exit 1 ;; esac
      - name: actor first, then the list
        run: |
          # ruleid: perun.gha.actor-allowlist-from-vars
          who="$GITHUB_ACTOR"
          grep -qxF "$who" <<< "${{ vars.TRUSTED_PUBLISHERS }}"
  # The rule cannot see where a variable is defined, so a job that declares an environment still flags (the message says to drop the lead then).
  with-environment:
    runs-on: ubuntu-latest
    environment: release
    steps:
      # ruleid: perun.gha.actor-allowlist-from-vars
      - if: contains(vars.RELEASERS, github.actor)
        run: ./publish.sh
'''

DEPLOY = r'''name: deploy
on: workflow_dispatch
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      # ruleid: perun.gha.actor-allowlist-from-vars
      - if: ${{ !contains(vars.DEPLOYERS, github.actor) }}
        run: exit 1
'''

ACTION = r'''name: gate
description: Fictional composite gate.
runs:
  using: composite
  steps:
    # ruleid: perun.gha.actor-allowlist-from-vars
    - if: contains(vars.ADMINS, github.actor)
      shell: bash
      run: ./publish.sh
'''

# Not valid YAML (unclosed flow mapping, stray bracket): a rule with `languages: [yaml]` loses the file to a parse error, this one must still flag it.
BROKEN = r'''name: broken
jobs: {{
  publish:
    # ruleid: perun.gha.actor-allowlist-from-vars
    if: contains(vars.RELEASERS, github.actor)
  ] :
'''

CI = r'''name: ci
on: pull_request
jobs:
  skip-bots:
    runs-on: ubuntu-latest
    # ok: perun.gha.actor-allowlist-from-vars
    if: github.actor != 'dependabot[bot]'
    steps:
      - run: ./test.sh
  literal-list:
    runs-on: ubuntu-latest
    # ok: perun.gha.actor-allowlist-from-vars
    if: contains(fromJSON('["jane-smith","john-doe"]'), github.actor)
    steps:
      - run: ./test.sh
  flag-and-bot-check:
    runs-on: ubuntu-latest
    # ok: perun.gha.actor-allowlist-from-vars
    if: vars.FEATURE_X == 'true' && github.actor != 'dependabot[bot]'
    steps:
      - run: ./test.sh
  unrelated-variable:
    runs-on: ubuntu-latest
    steps:
      # ok: perun.gha.actor-allowlist-from-vars
      - run: echo "deploying to ${{ vars.DEPLOY_REGION }} for ${{ github.actor }}"
      # ok: perun.gha.actor-allowlist-from-vars
      - run: echo "regions ${{ vars.ALLOWED_REGIONS }}"
      - run: echo "started by ${{ github.actor }}"
  code-owned-file:
    runs-on: ubuntu-latest
    steps:
      # ok: perun.gha.actor-allowlist-from-vars
      - run: grep -qxF "$GITHUB_ACTOR" .github/RELEASERS
  commented-out:
    runs-on: ubuntu-latest
    steps:
      # ok: perun.gha.actor-allowlist-from-vars
      # - if: contains(vars.RELEASERS, github.actor)
      - run: ./test.sh
  hint-only:
    runs-on: ubuntu-latest
    steps:
      # ok: perun.gha.actor-allowlist-from-vars
      - run: echo "${{ vars.TRUSTED_REGIONS }}"
  actor-only:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ github.actor }}"
'''

FILES = {
    ".github/workflows/release.yml": RELEASE,
    ".github/workflows/deploy.yaml": DEPLOY,
    ".github/workflows/ci.yml": CI,
    ".github/workflows/broken.yml": BROKEN,
    "action.yml": ACTION,
    ".github/actions/gate/action.yml": ACTION,
    ".github/actions/old/action.yaml": ACTION,
}
SKIPPED = {"docs/release-example.yml": RELEASE}  # not a workflow or action file: nothing in this copy may be reported
ANN = re.compile(r"^\s*#\s*(ruleid|ok): " + re.escape(RID) + r"\s*$")


def annotated(body, kind):
    """Line numbers of the lines each `# <kind>: <id>` comment points at (the next one)."""
    return {i + 1 for i, l in enumerate(body.split("\n"), 1) if (m := ANN.match(l)) and m.group(1) == kind}


assert all(annotated(b, "ruleid") or annotated(b, "ok") for b in FILES.values())
assert sum(len(annotated(b, "ruleid")) for b in FILES.values()) == 9 + 1 + 3 + 1  # annotations are not silently dropped
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for p, body in {**FILES, **SKIPPED}.items():
            os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
            open(os.path.join(d, p), "w").write(body)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--jobs", "1", "--json", "--quiet", "--", *FILES, *SKIPPED],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = {(x["path"], x["start"]["line"]) for x in r["results"] if x["check_id"].endswith(RID)}  # semgrep prefixes the id with the config's directory
    want = {(p, ln) for p, b in FILES.items() for ln in annotated(b, "ruleid")}
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
else:
    print("SKIP: semgrep not installed; the live fixture check did not run, the offline checks below do")

# Offline: structural pins on the rule text, then the rule's own three regexes replayed with Python's re over every fixture
# (the same PCRE subset in both engines). CI installs no semgrep, so dropping a guard (the comment-line skip, the step and job
# boundary, a name hint, an operand form) fails this file even when the live part is skipped.
SRC = open(RULES if os.path.isfile(RULES) else os.path.join(RULES, "gha.yml")).read()
assert SRC.count("\n- id: ") == 1 and f"\n- id: {RID}\n" in SRC and "\n  severity: WARNING\n" in SRC
assert "\n  languages: [regex]\n" in SRC  # not yaml: a file that fails YAML parsing must still be scanned
assert '\n    include: [".github/workflows/*.yml", ".github/workflows/*.yaml", "action.yml", "action.yaml"]\n' in SRC
quoted = lambda key: [s.replace("''", "'") for s in re.findall(rf"\n  (?:- )?{key}: '((?:[^']|'')*)'(?=\n)", SRC)]
(msg,), RX = quoted("message"), quoted("pattern-regex")
assert msg.startswith("[heuristic] ") and "write access" in msg and "environment variable" in msg and "code-owned file" in msg
assert len(RX) == 3 and all(h in "".join(RX) for h in ("allow", "releaser", "deployer", "approver", "admin", "maintainer", "trusted"))
for p, body in FILES.items():
    got = {body.count("\n", 0, m.start()) + 1 for rx in RX for m in re.finditer(rx, body)}
    assert got == annotated(body, "ruleid"), (p, "unexpected", sorted(got - annotated(body, "ruleid")), "missed", sorted(annotated(body, "ruleid") - got))
print("ok")
