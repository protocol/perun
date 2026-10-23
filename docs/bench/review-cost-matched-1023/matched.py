#!/usr/bin/env python3
"""Matched-harness review-cost bench (see PREREGISTERED.md). Both arms run on the DEFAULT Claude Code system prompt with
--exclude-dynamic-system-prompt-sections, same model, read-only tools, same 22 held-out cases, same PRODUCER output format.
  PERUN = the repo's shipped /review command (commands/review.md) plus the skill, installed in the workspace.
  TK    = the Anthropic pr-review-toolkit plugin (fetched at run time from its public upstream, pinned commit, SHA-256 checked; this bench
          does not vendor it), loaded with --plugin-dir, code-reviewer agent
          invoked through the Agent tool the way the plugin ships (not as --system-prompt).
Reuses confirm.py (cap/quota guards, ledgered claude call, decide()) and driver.py (split, judging, bootstrap) of review-cost-v2-1019.
usage: matched.py [dry-run [DIR]]  build every workspace, assert each arm's files, call nothing, no network (default). TK files are
                                   checked only when DIR holds a plugin fetched by `fetch`; otherwise that check is skipped, with a message
       matched.py fetch DIR        download the pinned plugin files into DIR (network), verify SHA-256
       matched.py run [N]     paid: quota probe, then the first N (default all 22) held-out cases, both arms, cap $4
       matched.py judge       free PCSS judges
       matched.py verdict     keep rule, writes results.json"""
import hashlib, json, re, shutil, sys, tempfile, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "docs/bench/review-cost-v2-1019"))
import confirm  # noqa: E402
import driver as d  # noqa: E402

OUT, ARMS, CAP = HERE / "runs-claude", ("PERUN", "TK"), 4.0
PLUGIN = None  # fetched plugin dir, set by run()
confirm.CAP, confirm.LEDGER = CAP, HERE / "ledger.jsonl"
UPSTREAM = "https://raw.githubusercontent.com/anthropics/claude-plugins-official/ce721c1f1d5da2c281588818e072ae01a05d2e73/plugins/pr-review-toolkit/"
TK_FILES = {".claude-plugin/plugin.json": "7aa64c91a9316ef3641df115414c07c7caee8f48368815dc2950483598321865",
            "agents/code-reviewer.md": "019395c3ce457460115cc703e2f4a86fed4bbe560dc58355051c4d877155d366"}
REVIEW_CMD, SKILL = ROOT / "commands/review.md", ROOT / ".claude/skills/deep-code-review"
COMMON = ["-p", "--setting-sources", "project,local", "--strict-mcp-config", "--no-session-persistence", "--output-format", "stream-json",
          "--verbose", "--exclude-dynamic-system-prompt-sections", "--max-budget-usd", str(confirm.RESERVE)]
PROMPT = {"PERUN": "/review FILE ./change.patch\n\n" + d.bc.PRODUCER,
          "TK": "Use the pr-review-toolkit:code-reviewer agent (Agent tool) to review this change, then answer with its findings in the format below.\n\n" + d.bc.PRODUCER}


def flags(arm):
    """claude flags for an arm. Never --system-prompt (the point of the bench); TK adds the Agent tool and its plugin dir."""
    tools = ["Read", "Grep", "Glob"] + (["Agent"] if arm == "TK" else [])
    return COMMON + ["--tools", ",".join(tools), "--allowedTools", *tools] + (["--plugin-dir", "pr-review-toolkit"] if arm == "TK" else [])


def check_plugin(plugin):
    """Raise SystemExit unless every TK_FILES file under plugin matches its pinned SHA-256."""
    for rel, sha in TK_FILES.items():
        f = Path(plugin) / rel
        if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest() != sha:
            raise SystemExit(f"plugin dir: {rel} missing or does not match the pinned SHA-256")


def fetch_plugin(dest):
    """Download the pinned plugin files (UPSTREAM, TK_FILES) into dest, failing on any SHA-256 mismatch. Needs the network.
    Every file is verified before any is written, so a mismatch leaves dest untouched."""
    got = {}
    for rel, sha in TK_FILES.items():
        got[rel] = urllib.request.urlopen(UPSTREAM + rel, timeout=60).read()
        if hashlib.sha256(got[rel]).hexdigest() != sha:
            raise SystemExit(f"fetch: {rel} does not match the pinned SHA-256 (upstream changed or fetch corrupted)")
    for rel, b in got.items():
        (Path(dest) / rel).parent.mkdir(parents=True, exist_ok=True)
        (Path(dest) / rel).write_bytes(b)
    return Path(dest)


def build(w, cid, arm, plugin=None):
    """Populate workspace w for (case, arm); returns the paths that must exist for that arm. TK needs the fetched plugin dir."""
    w = Path(w)
    (w / "change.patch").write_bytes((d.CORPUS / cid / "change.patch").read_bytes())
    if arm == "PERUN":
        (w / ".claude/commands").mkdir(parents=True)
        (w / ".claude/commands/review.md").write_bytes(REVIEW_CMD.read_bytes())
        shutil.copytree(SKILL, w / ".claude/skills/deep-code-review")
        return [".claude/commands/review.md", ".claude/skills/deep-code-review/SKILL.md"]
    shutil.copytree(plugin, w / "pr-review-toolkit")
    agent = w / "pr-review-toolkit/agents/code-reviewer.md"
    # ponytail: model pinned to the session model so both arms are same-model; frontmatter only, body untouched (dry-run asserts).
    agent.write_text(re.sub(r"(?m)^model: .*$", "model: inherit", agent.read_text(), count=1))
    return ["pr-review-toolkit/.claude-plugin/plugin.json", "pr-review-toolkit/agents/code-reviewer.md"]


def dry_run(plugin=None):
    """Build all 22 x 2 workspaces under a temp dir and assert files and invariants. No claude call, no network.
    Returns (case count, notes). The TK file check runs only when plugin is a fetched plugin dir; otherwise it is skipped and noted."""
    ids, notes = d.SPLIT["heldout"], []
    assert len(ids) == 22, ids
    arms = [a for a in ARMS if a != "TK" or plugin]
    if plugin:
        check_plugin(plugin)
    if "TK" not in arms:
        notes.append("SKIP TK file-presence check: plugin not fetched (no network in dry-run); run `matched.py fetch DIR` then `matched.py dry-run DIR`")
    for arm in ARMS:
        assert "--system-prompt" not in flags(arm) and "--exclude-dynamic-system-prompt-sections" in flags(arm), arm
    for arm in arms:
        for cid in ids:
            with tempfile.TemporaryDirectory(prefix="mbench-") as t:
                for rel in ["change.patch"] + build(t, cid, arm, plugin):
                    assert (Path(t) / rel).is_file(), f"{arm}/{cid}: missing {rel}"
                if arm == "TK":
                    a = (Path(t) / "pr-review-toolkit/agents/code-reviewer.md").read_text()
                    shipped = (Path(plugin) / "agents/code-reviewer.md").read_text().split("\n---\n", 1)[1]
                    assert "model: inherit" in a.split("\n---\n")[0] and a.split("\n---\n", 1)[1] == shipped, "agent body changed"
                else:
                    assert (Path(t) / ".claude/commands/review.md").read_text() == REVIEW_CMD.read_text()
    return len(ids), notes


def spent_for(arm, cid):
    """USD of every ledgered call (retries included) for (arm, case)."""
    rows = (json.loads(l) for l in confirm.LEDGER.read_text().splitlines())
    return sum(r.get("cost", 0) for r in rows if r.get("tag", "").startswith(f"{arm}/{cid}/"))


def review(cid, arm):
    p = OUT / arm / f"{cid}.json"
    if p.exists() and not json.loads(p.read_text()).get("error"):
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    for attempt in (1, 2):
        with tempfile.TemporaryDirectory(prefix="mbench-") as w:
            build(w, cid, arm, PLUGIN)
            confirm.FLAGS = flags(arm)  # ponytail: sequential, FLAGS is a module global; parallelize only with a per-call flags arg
            txt, err, use = confirm.call(PROMPT[arm], w, None, f"{arm}/{cid}/{attempt}")
        f = None if err else d.bc.parse_array(txt)
        err = err or ("" if f is not None else "no JSON array in output")
        p.write_text(json.dumps(dict(id=cid, arm=arm, findings=f or [], error=err, attempts=attempt, turns=use.get("turns") or 0,
                                     tokens=confirm.tokens(use), usage=use), indent=1))
        if not err:
            break


def run(limit=None):
    global PLUGIN
    d.OUT = OUT
    ids = d.SPLIT["heldout"][: int(limit) if limit else None]
    with tempfile.TemporaryDirectory(prefix="mbench-plugin-") as pd:
        PLUGIN = fetch_plugin(pd)  # before any paid call: a fetch or hash failure costs nothing
        with tempfile.TemporaryDirectory(prefix="mbench-") as t:
            confirm.call("Be terse. Reply ok.", t, "You answer in one word.", "probe")  # quota probe before any real call
        with open(confirm.LEDGER, "a") as f:
            f.write(json.dumps(dict(event="run_start", review_md_sha256=hashlib.sha256(REVIEW_CMD.read_bytes()).hexdigest(), cases=len(ids),
                                    tk_upstream=UPSTREAM, tk_sha256=TK_FILES)) + "\n")
        for cid in ids:
            for arm in ARMS:
                review(cid, arm)
            print(cid, f"spent {confirm.spent():.3f}", flush=True)


def judge():
    d.OUT = OUT
    for a in ARMS:
        d.stage(d.judge, a, d.SPLIT["heldout"])


def verdict():
    """Keep rule (PREREGISTERED.md): confirm.decide on F1(PERUN)-F1(TK) and the mean-dollar ratio PERUN/TK; tie at lower cost = keep."""
    d.OUT = OUT
    rows = {a: {c: d.loadt(a, c) for c in d.SPLIT["heldout"]} for a in ARMS}
    H = [c for c in d.SPLIT["heldout"] if rows["PERUN"][c] and rows["TK"][c]]
    mean = lambda xs: sum(xs) / max(1, len(xs))  # noqa: E731
    out = dict(n=len(H), dropped=[c for c in d.SPLIT["heldout"] if c not in H], spent_usd=round(confirm.spent(), 4), arms={})
    for a in ARMS:
        r = [rows[a][c] for c in H]
        out["arms"][a] = dict(f1=round(d.stats(r)[2], 3), usd_per_case=round(mean([spent_for(a, c) for c in H]), 5),
                              tokens=round(mean([x["tokens"] for x in r]), 1), turns=round(mean([x["turns"] for x in r]), 2))
    f1 = d.boot([rows["PERUN"][c] for c in H], [rows["TK"][c] for c in H])[2]
    ratio = out["arms"]["PERUN"]["usd_per_case"] / out["arms"]["TK"]["usd_per_case"]
    out["f1_perun_minus_tk"], out["cost_ratio_perun_over_tk"] = f1, round(ratio, 3)
    out["keep"] = confirm.decide(f1, ratio)
    (HERE / "results.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))


if __name__ == "__main__":
    m, a = (sys.argv[1] if len(sys.argv) > 1 else "dry-run").lstrip("-"), sys.argv[2:]
    if m == "dry-run":
        n, notes = dry_run(a[0] if a else None)
        print(f"dry-run ok: {n} cases, arms {[x for x in ARMS if x != 'TK' or a]}, no claude call, no network", *notes, sep="\n")
    elif m == "fetch":
        print("fetched and verified:", fetch_plugin(a[0]))
    else:
        {"run": run, "judge": judge, "verdict": verdict}[m](*a)
