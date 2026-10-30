#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=no fixed/faster/done claim on a delivery outcome without a measurement, review=2027-01-30
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
  claims. The message is compliant when it carries evidence, a before -> after pair with a unit, an outcome metric
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

A second Stop claim class, "unseen UI": a reply that says a UI surface (page, view, screen, chart, layout, dashboard, a
localhost URL) works, shows, renders, loads or is ready/done is flagged unless the session transcript (`transcript_path`;
only tool names, file paths and Bash command lines are read, never content) holds an image Read or screenshot tool call
AFTER both the last source edit (any Edit/Write, or an in-place sed/perl; UI files per lane_guard._UI_RE decide whether
there is UI work at all) and the last dev-server (re)start command; a screenshot older than either is a "stale server" or
stale capture. A hedge ("not visually checked") exempts only its own sentence. A load that returned HTTP 200 is not a
look: the incident was a page that loaded but rendered blank, off-frame. Only the last 2 MB of the transcript is read.
Same modes, note loop and fail-open as below.

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
SUBJECT = re.compile(r"\b(pipelines?|ci|gates?|trains?|queues?|merg\w+|land\w*|lead time|builds?|deploy\w*|runners?|"
                     r"flak\w*|latency|throughput|perf\w*|speed|slow\w*|risk|bottlenecks?|hooks?|wait\w*|backlog)\b", re.I)
COUNT = re.compile(r"\b\d+\s+(?:\w+\s+)?(?:PRs?|pull requests?|lanes?|tests?|files?|commits?|agents?|subagents?)\b"
                   r"(?:\s+\w+)?\s+(?:merged|landed|opened|spawned|added|touched|shipped|launched|running|in flight)",
                   re.I)
TALLY = re.compile(r"(?<![#\w])\d+\s+(?:\w+\s+)?(?:have\s+)?(?:merged|landed)\s+(?:today|so far|this (?:week|session|run)|since)\b",
                   re.I)
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
UI_SUBJECT = re.compile(r"\b(pages?|views?|screens?|charts?|layouts?|dashboards?|timelines?|localhost|127\.0\.0\.1)\b", re.I)
UI_WEAK = re.compile(r"\b(boards?|routes?)\b|(?<![-\w])ui(?![-\w])", re.I)  # ambiguous nouns: only a visual verb makes a claim
UI_CLAIM = re.compile(r"\b(shows?|showing|renders?|rendering|rendered|displays?|displayed|works?|working|loads?|loaded|"
                      r"ready|done|live|(?:is|are|now|['’]s)\s+up|visible|looks? (?:good|right|correct|fine))\b", re.I)
UI_VISUAL = re.compile(r"\b(shows?|showing|renders?|rendering|rendered|displays?|displayed|looks?|ready|visible)\b", re.I)
FENCE = re.compile(r"```.*?```", re.S)  # the UI class keeps inline code: a bare URL is often written in backticks
DOC = re.compile(r"\.(?:md|txt|rst)$", re.I)
UI_HEDGE = re.compile(r"\b(not (?:yet )?(?:visually|screenshotted|looked at|seen|eyeballed)|no screenshots?|"
                      r"visually (?:unchecked|unverified)|unchecked visually|haven['’]?t (?:looked|seen|screenshotted))", re.I)
LOCAL = re.compile(r"localhost|127\.0\.0\.1", re.I)
SERVER = re.compile(r"\b(?:(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:dev|start)|next\s+dev|vite(?![\w.-]|\s+build\b)|turbo(?:\s+run)?\s+(?:dev|start|serve)|"
                    r"docker[ -]compose\s+up|rails\s+s(?:erver)?|python3?\s+-m\s+http\.server)\b|"
                    r"(?:^|[;&|(]\s*)make(?:\s+[\w-]+)*?\s+(?:dev|start|serve|up)\b")
SHOT_CMD = re.compile(r"\bplaywright\s+screenshot\b|\.screenshot\(|--screenshot|(?:^|[;&|(]\s*)screencapture\b")
INPLACE = re.compile(r"\b(?:sed|perl)\s+(?:-\w+\s+)*-\w*i\b|--in-place")
IMAGE = re.compile(r"\.(?:png|jpe?g|gif|webp)$", re.I)
TAIL = 2 * 1024 * 1024  # ponytail: edits and screenshots older than the last 2 MB are unseen (an old shot is missed, so it flags; an old edit hides the UI work, so only localhost claims flag); raise TAIL or index the transcript if that bites
UI_REASON =("Unseen UI claim: \"{snip}\" ({why}). Take a screenshot at a phone and a desktop width from a fresh dev "
             "server on this commit, with fixture data and with the data source off, look at it, then claim; or say "
             "\"not visually checked\". HTTP 200 is not a look.")
UI_NUDGE = ("UI check: your last reply claimed \"{snip}\" ({why}). Screenshot after the last UI edit and server "
            "restart and look at it, or say \"not visually checked\".")


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


def _sentences(text, code=CODE):
    return [s for s in re.split(r"(?<=[.!?;])\s+|\n+", code.sub(" ", text)) if s.strip()]


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


def ui_claims(text):
    """UI-surface claim sentences in `text` (stripped, at most 120 chars). Same negation/modal/question skips as claims().

    Inline code is kept (fences are dropped). A hedge exempts only the sentence that carries it.
    """
    out = []
    for s in _sentences(text or "", FENCE):
        verbs = UI_CLAIM if UI_SUBJECT.search(s) else UI_VISUAL if UI_WEAK.search(s) else None
        if s.rstrip().endswith("?") or not verbs or HEDGE.search(s) or UI_HEDGE.search(s):
            continue
        if any(not NEGATED.search(s[:m.start()]) and not MODAL.search(s[:m.start()]) for m in verbs.finditer(s)):
            out.append(s.strip()[:120])
    return out


def _ui_events(path):
    """(last UI-file edit, last source edit, last dev-server start, last screenshot) as line indexes into the last
    TAIL bytes of the transcript, -1 when absent. Names, paths, actions and Bash command lines only."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lane_guard import _UI_RE
    ui = edit = server = shot = -1
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        f.seek(max(0, size - TAIL))
        if size > TAIL:
            f.readline()  # drop the partial first line
        for i, line in enumerate(f):
            try:
                content = json.loads(line.decode("utf-8", "replace"))["message"]["content"]
            except (ValueError, KeyError, TypeError):
                continue
            for c in content if isinstance(content, list) else []:
                if not isinstance(c, dict) or c.get("type") != "tool_use":
                    continue
                name, inp = str(c.get("name") or ""), c.get("input") or {}
                target = str(inp.get("file_path") or inp.get("notebook_path") or "")
                cmd = str(inp.get("command") or "") if name == "Bash" else ""
                if name in ("Edit", "Write", "MultiEdit", "NotebookEdit") and not DOC.search(target):
                    edit = i
                    ui = i if _UI_RE.search(target) else ui
                if cmd and INPLACE.search(cmd):
                    edit = i
                if cmd and SERVER.search(cmd):
                    server = i
                if ("screenshot" in name.lower() or "screenshot" in str(inp.get("action") or "").lower()
                        or name == "Read" and IMAGE.search(target) or cmd and SHOT_CMD.search(cmd)):
                    shot = i
    return ui, edit, server, shot


def ui_violation(text, transcript_path):
    """(claim sentence, why) when `text` claims a UI works and the transcript has no fresh screenshot, else None.

    Fresh = after the last source edit and the last dev-server start. With no UI-file edit or server start in the
    transcript tail, only a claim naming a localhost URL is checked. Raises OSError on an unreadable transcript (caller fails open).
    """
    found = ui_claims(text)
    if not found or not transcript_path:
        return None
    ui, edit, server, shot = _ui_events(transcript_path)
    if shot > max(edit, server):
        return None
    if shot >= 0:
        return found[0], "screenshot older than the last edit" if edit > server else "stale server: screenshot predates the last dev-server start"
    if max(ui, server) >= 0 or LOCAL.search(text):
        return found[0], "no screenshot after the UI work"
    return None


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
        msg = data.get("last_assistant_message") or ""
        snip, ui = stop_violation(msg), None
        if snip:
            reason = STOP_REASON.format(snip=snip)
        else:
            ui = ui_violation(msg, data.get("transcript_path"))
            if not ui:
                return None
            snip, reason = ui[0], UI_REASON.format(snip=ui[0], why=ui[1])
        if mode == "block":
            return {"decision": "block", "reason": reason}
        try:  # the owner-only systemMessage still goes out if the note cannot be written
            path = note_path(data)
            if path:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    json.dump({"claim": snip, "ui": ui[1] if ui else ""}, f)
        except OSError:
            pass
        return {"systemMessage": reason}
    if event == "UserPromptSubmit":
        path = note_path(data)
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                note = json.load(f)
            claim, why = str(note.get("claim") or "")[:120], str(note.get("ui") or "")[:80]
        except (OSError, ValueError, AttributeError):  # unreadable note: drop it, say nothing
            claim = why = ""
        os.remove(path)
        if not claim:
            return None
        nudge = UI_NUDGE.format(snip=claim, why=why) if why else NUDGE.format(snip=claim)
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": nudge}}
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
    assert ui_claims("The new page now shows at http://localhost:3000/board.")
    assert not ui_claims("Is the page ready?") and not ui_claims("The page is not ready yet.")
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
