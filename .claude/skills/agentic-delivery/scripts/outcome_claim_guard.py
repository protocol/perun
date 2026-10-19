#!/usr/bin/env python3
"""outcome_claim_guard.py — Stop + PreToolUse + UserPromptSubmit hook: no "fixed / faster / done" on delivery outcomes without a measurement.

WHY: a coordinator called pipeline work "done" and "improved" at PR open, reported PRs merged and lanes spawned as
progress, and the gate time it was tuning rose about fourfold while its own fixes waited in the same slow queue. A
fix announced as ending a risk "once it lands" then failed in every later run. Output (PRs, lanes, tests, files) was
reported as outcome, and nothing measured before and after. This hook makes the claim and its evidence travel together.

Two modes, chosen by `hook_event_name` in the stdin JSON:
- Stop: scans `last_assistant_message` (fenced and inline code removed) for an outcome claim: a claim word (fixed,
  improved, faster, resolved, working, done, ends the risk, no longer, ...) in the same sentence as a delivery subject
  (pipeline, CI, gate, train, queue, merge, build, flake, risk, ...), or an output count framed as progress ("9 PRs
  merged" next to "progress"/"shipped"/a claim word). Negated, questioned or modal ("would", "might") claims are not
  claims, nor are a few action idioms bound directly to the claim word: a deliverable as the subject of "done" ("the
  audit is done"), "fixed one error in the report", "resolved the merge conflicts" with no delivery word after them,
  "6 issues already fixed" in a sentence that closes or dedups, and a "pre-merge" check. Nothing else in the sentence
  can launder a claim, and every other claim in the message is still scanned. The message is compliant when it carries evidence, a before -> after pair with a unit, an outcome metric
  word (lead time, gate/CI/train minutes, landed per hour, failure rate, ...) and a merged-code reference (a commit
  sha, or a PR number next to "merged"/"landed"), or an honest hedge ("opened, unmeasured", "not yet measured").
  Counts of PRs, lanes, tests or files are never evidence. A violation: `block` returns {"decision": "block"} once
  (never when `stop_hook_active` is true, so it cannot loop); `warn` returns a `systemMessage` for the owner.
- PreToolUse (Bash): on `gh pr create` or `gh pr merge` whose diff touches a pipeline path (policy key
  `outcome_guard_paths`, a list of fnmatch globs; default DEFAULT_PATHS: workflows, git hooks, train/gate/CI
  scripts), looks for a `pipeline_profile.py compare` verdict line (`KEEP  dropped ...`) in the PR body or the commit
  messages; the last verdict wins. KEEP passes. REVERT, UNVERIFIED or no verdict: `block` denies the call, `warn` adds
  the reason to Claude's context and lets it run. `create` reads the diff and commits with git (base `--base`/`-B`,
  else origin/HEAD) and the body like comms_guard.py does; `merge` reads one `gh pr view --json body,files,commits`.

UserPromptSubmit closes the loop in `warn` mode: the Stop `systemMessage` reaches only the owner, so the Stop check also
writes a one-claim note for the session (needs `session_id`) and the next UserPromptSubmit emits it once as
`hookSpecificOutput.additionalContext` (the claim, what evidence is missing, "measure or hedge") and deletes it, so the model
learns its claim was unmeasured. `block` mode writes no note (the model already got the reason). Notes live in
$PERUN_OUTCOME_DIR, else <cache>/perun/outcome-claim (beside the ceo-altitude counters), one file per session_id.

Mode: env PERUN_OUTCOME_GUARD=off|warn|block, else policy key `outcome_guard` (`perun_policy.py set outcome_guard
block`), else DEFAULT_MODE. DEFAULT_MODE is `warn`: replaying the Stop check over a few hundred real coordinator replies, a
hand-labelled sample showed well over 10% of flags landing on honest replies, so blocking by default would bounce them.
Register as `python3 ".../outcome_claim_guard.py" || true` on Stop, UserPromptSubmit and PreToolUse (Bash). Fail open:
bad stdin, an unreadable policy or note, a git or gh failure or any error prints nothing and exits 0. Side effects:
read-only git/gh queries; in warn mode one small note file per session (written on Stop, deleted on the next
UserPromptSubmit). Limits: a message-level hedge covers every claim in that message; regexes are English-only.
Test: scripts/test_outcome_claim_guard.py.
"""
import fnmatch
import json
import os
import re
import subprocess
import sys

MODES = ("off", "warn", "block")
DEFAULT_MODE = "warn"
DEFAULT_PATHS = (".github/workflows/*", ".githooks/*", ".husky/*", ".gitlab-ci.yml", "*/hooks/*", "*train*.sh",
                 "*train*.py", "*_gate.py", "*-gate.sh", "*gates.sh", "*/ci/*")

CLAIM = re.compile(r"\b(fixed(?!\s+PRs?\b)|fixes(?=\s+(?:the|a|an|it|this|that|all|both)\b|\s+\[?#\d)|prevents|blocks it|stops it|improved|improves|"
                   r"faster|quicker|sped up|speeds? up|resolved|resolves|solved|working (?:now|again|fine)|"
                   r"works(?: now| again)?|done|ends? the risk|ended the risk|risk is gone|eliminat\w+|unblocked|"
                   r"no longer)\b", re.I)
SUBJECT = re.compile(r"(?<!\bpre-)\b(pipelines?|ci|gates?|trains?|queues?|merg\w+|land\w*|lead time|builds?|deploy\w*|runners?|"
                     r"flak\w*|latency|throughput|perf\w*|speed|slow\w*|risk|bottlenecks?|hooks?|wait\w*|backlog)\b", re.I)
COUNT = re.compile(r"\b\d+\s+(?:\w+\s+)?(?:PRs?|pull requests?|lanes?|tests?|files?|commits?|agents?|subagents?)\b"
                   r"(?:\s+\w+)?\s+(?:merged|landed|opened|spawned|added|touched|shipped|launched|running|in flight)",
                   re.I)
TALLY = re.compile(r"(?<![#\w])\d+\s+(?:\w+\s+)?(?:have\s+)?(?:merged|landed)\s+(?:today|so far|this (?:week|session|run)|since)\b",
                   re.I)
# Action idioms that are not outcome claims. Each skip is bound to the claim word (a deliverable, conflict or issue
# elsewhere in the sentence must not launder a claim), and the whole sentence is still scanned for other claims.
_DOC = r"(?:audits?|reports?|drafts?|logs?|notes|docs?|documents?|summary|research|plan|standup|handoff|memo|write-?ups?)"
DOC_BEFORE = re.compile(rf"\b{_DOC}\b(?:\s+\(?#?\d+\)?)?(?:\s+(?:is|are|was|were))?\s*$", re.I)  # "the audit is done"
DOC_AFTER = re.compile(rf"\W*(?:(?:the|a|an|my|our)\s+)?(?:\w+\s+)?{_DOC}\b", re.I)  # "Done: the handoff note"
EDIT = re.compile(rf"\s+(?:one|an?|the|\d+)\s+(?:\w+\s+)?(?:errors?|typos?|mistakes?|wording)\s+(?:in|on)\s+(?:the|my|this)\s+{_DOC}\b", re.I)
CONFLICT = re.compile(r"\s+(?:(?:the|all|any|both|\d+|merge|git)\s+)*conflicts?\b(.*)$", re.I)  # "resolved the merge conflicts on #5"
ALREADY = re.compile(r"(?:\d+|issues|tickets|bugs)\s+already[\s-]+$", re.I)  # "14 already fixed" ...
TRIAGE = re.compile(r"\b(?:clos\w+|duplicates?|triag\w+)\b", re.I)  # ... in a sentence that closes or dedups
NOUN_FIX = re.compile(r"(?:^|\s)(?!(?:it|which|that|now|also|\d+)\b)\w+\s+$", re.I)  # "pipeline fixes #12" is a noun
PROGRESS = re.compile(r"\b(progress|productive|momentum|velocity|on track|shipped|delivered|wins?)\b", re.I)
NEGATED = re.compile(r"(?:\b(?:not|no|never|nothing|without|until|unless|being)|n['’]t)\W+(?:\w+\W+){0,2}$", re.I)
MODAL = re.compile(r"\b(would|could|might|may|should|expected to|estimate\w*|hypothes\w+|if|must|have to|has to|"
                   r"needs? to|to be|after|before)\b", re.I)
HEDGE = re.compile(r"\b(unmeasured|not (?:yet )?measured|no measurement|unverified|not (?:yet )?verified|"
                   r"impact unknown|effect unknown|pending (?:measurement|verification)|no result yet|"
                   r"no before/after|measure (?:it )?(?:next|after|once))\b", re.I)
UNIT = r"(?:ms|s|sec|secs|seconds|m|min|mins|minutes|h|hr|hrs|hours|%|/h|/hr|per hour|/\d+)"
BEFORE_AFTER = re.compile(rf"\d[\d.,]*\s*{UNIT}?\s*(?:→|->|=>|⇒|\bto\b)\s*\d[\d.,]*\s*{UNIT}?(?!\w)", re.I)
METRIC = re.compile(r"\b(lead time|gate|train|ci|queue|wall|landed per hour|landed/h|per hour|throughput|failure rate|"
                    r"fail rate|flake rate|pass rate|minutes|median|p50|p90|runs)\b", re.I)
SHA = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
MERGED_PR = re.compile(r"\b(?:merged|landed)\b[^.\n]{0,40}#\d+|#\d+[^.\n]{0,40}\b(?:merged|landed)\b", re.I)
VERDICT = re.compile(r"\b(KEEP|REVERT|UNVERIFIED)\s+(?=dropped|did not drop|metric |only \d|no sample)")
VALUE_FLAGS = ("--body", "-b", "--body-file", "-F", "--subject", "-t", "--match-head-commit", "--author-email", "-A")
GH_PR = re.compile(r"\bgh\s+pr\s+(create|merge)\b")
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)

STOP_REASON = ("Unmeasured outcome claim: \"{snip}\". Give before -> after on an outcome metric (lead time, gate/CI "
               "minutes, landed per hour, failure rate) tied to a merged sha or PR, or restate it as \"opened, "
               "unmeasured\". PR, lane, test and file counts are output, not outcome.")
PR_REASON = ("This PR touches pipeline paths ({paths}) and carries {got}. Measure it: `pipeline_profile.py compare "
             "BEFORE.json AFTER.json --metric ...` and paste the verdict line into the PR body; only KEEP passes. "
             "Until then call it unmeasured, not faster or fixed.")
NUDGE = ("Outcome check: your last reply claimed \"{snip}\" with no before -> after on an outcome metric tied to a "
         "merged sha or PR. Measure it or hedge (\"opened, unmeasured\").")


def note_path(data):
    """The pending-note path for this event's session, or None without a session_id. Raises OSError with no absolute cache dir."""
    sid = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id") or ""))
    if not sid:
        return None
    base = os.environ.get("PERUN_OUTCOME_DIR")
    if not base:
        cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
        if not os.path.isabs(cache):
            raise OSError("no absolute cache dir: set HOME, XDG_CACHE_HOME or PERUN_OUTCOME_DIR")
        base = os.path.join(cache, "perun", "outcome-claim")
    return os.path.join(base, sid + ".json")


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?;])\s+|\n+", CODE.sub(" ", text)) if s.strip()]


def claims(text):
    """Outcome-claim sentences in `text` (stripped, at most 120 chars each); [] when none. Pure."""
    out = []
    for s in _sentences(text or ""):
        if s.rstrip().endswith("?"):
            continue
        hit = False
        for m in CLAIM.finditer(s):
            before = s[:m.start()]
            if m.group(0).lower() == "fixes" and "#" in s[m.end():m.end() + 3] and NOUN_FIX.search(before):
                continue
            word = m.group(0).lower()
            if word == "done" and (DOC_BEFORE.search(before) or not before.strip(" *_") and DOC_AFTER.match(s, m.end())):
                continue  # a deliverable is finished, not an outcome reached
            if word in ("fixed", "fixes", "resolved", "resolves", "solved"):
                cm = CONFLICT.match(s, m.end())
                if (EDIT.match(s, m.end()) or cm and not SUBJECT.search(cm.group(1))
                        or ALREADY.search(before) and TRIAGE.search(s)):
                    continue
            if SUBJECT.search(s) and not NEGATED.search(before) and not MODAL.search(before):
                hit = True
                break
        if not hit and (TALLY.search(s) or COUNT.search(s) and (PROGRESS.search(s) or CLAIM.search(s))):
            hit = True
        if hit:
            out.append(s.strip()[:120])
    return out


def evidenced(text):
    """True when `text` carries a before -> after pair with a unit, an outcome metric word and a merged-code ref."""
    t = CODE.sub(lambda m: m.group(0).strip("`"), text or "")
    pair = any(re.search(UNIT, m.group(0)) for m in BEFORE_AFTER.finditer(t))
    return pair and bool(METRIC.search(t)) and bool(SHA.search(t) or MERGED_PR.search(t))


def stop_violation(text):
    """The first unmeasured claim sentence, or None when the message is compliant. Pure."""
    found = claims(text)
    if not found or HEDGE.search(text or "") or evidenced(text):
        return None
    return found[0]


def verdict(text):
    """The last `pipeline_profile.py compare` verdict word in `text` (KEEP/REVERT/UNVERIFIED), or None."""
    found = VERDICT.findall(text or "")
    return found[-1] if found else None


def _run(args, cwd):
    p = subprocess.run(args, cwd=cwd or None, capture_output=True, text=True, timeout=8)
    if p.returncode:
        raise OSError(p.stderr.strip())
    return p.stdout


def _flag(cmd, names):
    m = re.search(rf"(?:^|\s)(?:{names})(?:=|\s+)([\"']?)([^\s\"']+)\1", cmd)
    return m.group(2) if m else None


def pr_facts(cmd, cwd):
    """(changed paths, body + commit text) for a `gh pr create|merge` command; raises on a git/gh failure."""
    m = GH_PR.search(cmd)
    tail = cmd[m.start():]
    if m.group(1) == "create":
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, here)
        import comms_guard
        got = comms_guard.extract("Bash", {"command": cmd}, cwd)
        base = _flag(tail, r"--base|-B")
        if base:
            base = "origin/" + base if not base.startswith("origin/") else base
        else:
            base = _run(["git", "rev-parse", "--abbrev-ref", "origin/HEAD"], cwd).strip() or "origin/main"
        paths = _run(["git", "diff", "--name-only", base + "...HEAD"], cwd).split()
        text = (got[1] if got else "") + "\n" + _run(["git", "log", "--format=%B", base + "..HEAD"], cwd)
        return paths, text
    words, sel, repo = re.split(r"[;&|]", tail, 1)[0].split()[3:], [], []
    while words:
        w = words.pop(0)
        if w in ("--repo", "-R") and words:
            repo = ["--repo", words.pop(0)]
        elif w.startswith("--repo="):
            repo = ["--repo", w.split("=", 1)[1]]
        elif w in VALUE_FLAGS and words:
            words.pop(0)
        elif not w.startswith("-") and not sel:
            sel = [w]
    pr = json.loads(_run(["gh", "pr", "view", *sel, *repo, "--json", "body,files,commits"], cwd))
    paths = [f.get("path", "") for f in pr.get("files") or []]
    text = (pr.get("body") or "") + "\n" + "\n".join(
        (c.get("messageHeadline") or "") + "\n" + (c.get("messageBody") or "") for c in pr.get("commits") or [])
    return paths, text


def policy():
    """(mode, path globs): env PERUN_OUTCOME_GUARD, else policy `outcome_guard`, else DEFAULT_MODE. Unreadable = defaults."""
    mode, globs = None, DEFAULT_PATHS
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import perun_policy
        pol = perun_policy.load()
        mode, globs = pol.get("outcome_guard"), pol.get("outcome_guard_paths") or DEFAULT_PATHS
    except Exception:  # fail open: a broken policy reads as the defaults
        pass
    env = (os.environ.get("PERUN_OUTCOME_GUARD") or "").strip().lower()
    mode = env if env in MODES else mode if mode in MODES else DEFAULT_MODE
    return mode, tuple(globs)


def handle(data, mode, globs):
    """The hook's JSON reply for one stdin event, or None for no output. Raises on git/gh failure (caller fails open)."""
    if mode == "off":
        return None
    event = data.get("hook_event_name") or "Stop"
    if event == "Stop":
        if data.get("stop_hook_active"):
            return None
        snip = stop_violation(data.get("last_assistant_message") or "")
        if not snip:
            return None
        reason = STOP_REASON.format(snip=snip)
        if mode == "block":
            return {"decision": "block", "reason": reason}
        try:  # the owner-only systemMessage still goes out if the note cannot be written
            path = note_path(data)
            if path:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    json.dump({"claim": snip}, f)
        except OSError:
            pass
        return {"systemMessage": reason}
    if event == "UserPromptSubmit":
        path = note_path(data)
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                claim = str(json.load(f).get("claim") or "")[:120]
        except (OSError, ValueError, AttributeError):  # unreadable note: drop it, say nothing
            claim = ""
        os.remove(path)
        if not claim:
            return None
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": NUDGE.format(snip=claim)}}
    cmd = (data.get("tool_input") or {}).get("command")
    if event != "PreToolUse" or data.get("tool_name") != "Bash" or not isinstance(cmd, str) or not GH_PR.search(cmd):
        return None
    paths, text = pr_facts(cmd, str(data.get("cwd") or ""))
    hits = [p for p in paths if any(fnmatch.fnmatch(p, g) for g in globs)]
    v = verdict(text)
    if not hits or v == "KEEP":
        return None
    reason = PR_REASON.format(paths=", ".join(hits[:3]) + (" ..." if len(hits) > 3 else ""),
                              got="a %s verdict" % v if v else "no pipeline_profile.py compare verdict")
    out = {"hookEventName": "PreToolUse"}
    if mode == "block":
        out.update(permissionDecision="deny", permissionDecisionReason=reason)
    else:
        out["additionalContext"] = "Outcome check (advisory, the call goes ahead): " + reason
    return {"hookSpecificOutput": out}


def selftest():
    """Planted cases: the guard fires on unmeasured claims and stays quiet on hedged or measured ones."""
    assert stop_violation("Fix for the merge lock is in; it ends the risk once it lands.")
    assert stop_violation("Great progress: 9 PRs merged and 4 lanes spawned.")
    assert not stop_violation("Gate fix opened as #12, unmeasured.")
    assert not stop_violation("CI is faster: gate median 820s -> 240s over 10 runs after a1b2c3d merged.")
    assert verdict("REVERT  did not drop\nKEEP  dropped 30.0% (10m -> 7m) [n=5]") == "KEEP"
    print("outcome_claim_guard selftest: ok")
    return 0


def main():
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    try:
        mode, globs = policy()
        if mode == "off":
            return 0
        out = handle(json.load(sys.stdin), mode, globs)
        if out:
            print(json.dumps(out))
    except Exception:  # fail open: a broken quality hook must never block work
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
