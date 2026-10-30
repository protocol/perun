#!/usr/bin/env python3
"""spend_hub.py: spend per day, project, model and session over Claude Code transcripts, plus the top waste levers.

WHY: issue "budget and spend tracking per session and per project" and the token-usage goal. Perun routes spend reading to
ccusage (MIT, https://github.com/ccusage/ccusage) when it is installed and falls back to token_report.py's own reader
(`build_rollup`) when it is not. Waste ranking has no fetched OSS counterpart, so it is token_report.py's `lever_ranking`
summed over the biggest sessions in the window, each lever tied to the setting or behaviour to change.

USAGE: spend_hub.py [--projects DIR] [--since YYYY-MM-DD] [--sessions N] [--top N] [--max-mb MB] [--no-ccusage] [--json]

BEHAVIOUR
- ccusage is used only when it is on PATH and neither --projects nor CLAUDE_CONFIG_DIR is set (so it reads the same logs as the
  fallback). It runs `ccusage claude daily --json --offline [--instances]`; output that is not the documented shape
  (ccusage.com/guide/json-output: `daily` rows and `totals`, `projects`) means a note and the fallback, never a guess.
- Sessions come from token_report.py always (ccusage's session JSON is documented in two shapes), ranked by USD, unpriced last.
- token_report.py never turns a gap into $0: a model with no rate row stays UNPRICED (listed as `unpriced: <models>`) and a transcript
  it cannot read is counted (`unreadable: N sessions`). Either makes its total a lower bound and the report says so; the ccusage
  parity line is skipped for a lower-bound total.
- Waste: the --sessions biggest sessions by USD in the window, skipping any session whose main and lane transcripts together exceed
  --max-mb (default token_report's NUDGE_MAX_BYTES; build_report holds every file in memory). Skipped sessions are counted and the
  spend coverage is printed. Savings levers: share = summed lever saving / summed main + lane input-equivalent of the measured
  sessions: an UPPER BOUND, not a bill, and levers overlap, so the shares are not additive. The orchestrator-tier row is listed apart
  as an exposure (input-eq on a top-tier main): not a saving, not additive.
- Lever state comes from the user-level settings and the environment only: a project's own settings (here, the cwd's) would mute a
  lever for every project. A lever whose key is set is skipped; with unreadable user settings it is listed as state unknown.
- Reads usage, timestamps, model ids and tool-result sizes only; never message text; writes nothing. Exit 0, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import token_report as tr  # noqa: E402

# lever key -> (lever-name prefix in lever_ranking, concrete change)
RECIPES = {
    "pin": ("pin main cache", 'set "promptCacheTtl": "1h" in settings.json (after 5 idle minutes the default cache expires and the next turn rewrites the whole context)'),
    "compact": ("auto-compact", f'set "autoCompactWindow": {tr.AUTO_COMPACT_WINDOW} in settings.json, or /compact at task breaks (a long context is resent every turn)'),
    "tail": ("lower LANE_TOOL_CAP", "set env LANE_TOOL_CAP below the p90 lane length (token_report.py --advise --fix-plan prints it for one session); long lanes resend their context"),
    "tooloutput": (tr.TOOL_LEVER, f'set "bashOutputMaxChars": {tr.BASH_OUTPUT_START} in settings.json; pipe long command output through head or tail'),
    "tier": ("orchestrator tier", "default the main session to a mid-tier model and escalate to the top tier for a named hard step"),
}


EXPOSURE = "exposure (not a saving, not additive)"


def ccusage_spend(exe: str, since: datetime):
    """Daily, per-model and per-project USD rows `[label, usd, []]` from ccusage, or None when it fails or its JSON lacks the documented keys."""
    def run(*extra):
        out = subprocess.run([exe, "claude", "daily", "--json", "--offline", "--since", since.strftime("%Y%m%d"), *extra],
                             capture_output=True, text=True, timeout=180, check=True).stdout
        return json.loads(out)

    def rows(by: dict) -> list:
        return [[k, v, []] for k, v in sorted(by.items(), key=lambda kv: -kv[1])]
    try:
        d, g = run(), run("--instances")
        models: Counter = Counter()
        for r in d["daily"]:
            for m in r["modelBreakdowns"]:
                models[m["modelName"]] += float(m["cost"])
        return {"source": "ccusage", "total_usd": float(d["totals"]["totalCost"]),
                "days": [[r["date"], float(r["totalCost"]), []] for r in d["daily"]], "models": rows(models),
                "projects": rows({k: sum(float(r["totalCost"]) for r in v) for k, v in g["projects"].items()})}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError):
        return None


def perun_spend(roll: dict) -> dict:
    """The same rows from token_report.build_rollup(by="day", group="project"). A model with no rate row keeps usd None (never 0); the total prices the rest only."""
    models: dict = {}
    for b in roll["buckets"]:
        for m, v in b["models"].items():
            models[m] = None if v["usd"] is None else (models.get(m) or 0.0) + v["usd"]
    return {"source": "token_report.py", "total_usd": roll["total_usd"],
            "days": [[b["bucket"], b["usd"], b["unpriced_models"]] for b in roll["buckets"]],
            "models": [[m, u, []] for m, u in sorted(models.items(), key=lambda kv: (kv[1] is None, -(kv[1] or 0)))],
            "projects": [[g["group"], g["usd"], g["unpriced_models"]] for g in roll["groups"]]}


def transcript_bytes(path: str) -> int:
    """Bytes build_report reads for one session: its main transcript plus every lane under `<session>/subagents`."""
    sdir = os.path.join(path[: -len(".jsonl")], "subagents")
    lanes = [os.path.join(sdir, n) for n in os.listdir(sdir) if n.endswith(".jsonl")] if os.path.isdir(sdir) else []
    return sum(os.path.getsize(p) for p in [path, *lanes])


def waste(sessions: list, projects: str, since: datetime, top: int, limit: int, max_bytes: int) -> dict:
    """Savings levers (and the tier exposure, apart) over the `limit` first of `sessions` that fit `max_bytes` (see the module doc for the share and what is skipped)."""
    dirs = {os.path.basename(os.path.normpath(d)): d for d in tr.rollup_dirs(projects)}
    # os.devnull as the project: only the user layer and the environment are read (a project layer would mute levers for every project)
    cfg, env, _mcp, bad = tr.load_settings(os.devnull)
    is_set = {k for k, names in tr.LEVER_KEYS.items() if any(n in cfg or n in env for n in names)}
    unknown = set(tr.LEVER_KEYS) - is_set if bad or not tr.user_config_dir() else set()
    seen: set = set()
    ie = sub = expo = 0.0
    sav: Counter = Counter()
    n = skipped = 0
    got, every = 0.0, sum(r["usd"] or 0.0 for r in sessions)  # priced USD of the sessions measured / of all in-window sessions (an unpriced session counts 0)
    for r in sessions:
        if n >= limit:
            break
        path = os.path.join(dirs[r["project"]], r["session"] + ".jsonl")
        if transcript_bytes(path) > max_bytes:
            skipped += 1
            continue
        rep = tr.build_report(path, since, 1, tr.DEFAULT_RATES, seen=seen)
        n += 1
        got += r["usd"] or 0.0
        s_ie = rep["main"]["input_equivalent"] + rep["subagents_totals"]["input_equivalent"]
        ie, sub = ie + s_ie, sub + rep["subagents_totals"]["input_equivalent"]
        for lv in rep["lever_ranking"]:
            key = next((k for k, (p, _) in RECIPES.items() if lv["lever"].startswith(p)), None)
            if key == "tier":  # no computed saving: the measured top-tier main input-eq
                expo += rep["tier_split"]["main_top_tier_share_of_total_ie"] * s_ie
            elif key:
                sav[key] += lv["saving_ie"]
    rows = [{"lever": RECIPES[k][0], "share": round(v / ie, 4), "change": RECIPES[k][1], "state": "unknown" if k in unknown else "unset"}
            for k, v in sav.most_common() if ie and v > 0 and k not in is_set]
    return {"max_mb": max_bytes // 10**6, "measured": n, "spend_coverage": round(got / every, 4) if every else 0.0,
            "skipped_over_cap": skipped, "subagent_share": round(sub / ie, 4) if ie else 0.0,
            "already_set": sorted(RECIPES[k][0] for k in is_set if k in sav), "levers": rows[:top],
            "exposure": {"kind": EXPOSURE, "lever": RECIPES["tier"][0], "share": round(expo / ie, 4), "change": RECIPES["tier"][1]}
            if ie and expo > 0 else None}


def render(rep: dict) -> str:
    """Plain-text report of a `build` result: spend by day, project, model, session, then the savings levers and the tier exposure."""
    sp, w = rep["spend"], rep["waste"]
    own = sp["source"] == "token_report.py"
    out = [f"spend {tr._usd(sp['total_usd'], rep['unpriced'] if own else ())} since {rep['since']} (source: {sp['source']})"]
    if rep["unpriced"]:
        out.append("unpriced: " + ", ".join(rep["unpriced"]) + " (token_report.py has no rate row for them: UNPRICED, never $0)")
    if any(rep["unreadable"].values()):
        out.append(f"unreadable: {rep['unreadable']['sessions']} sessions, {rep['unreadable']['lanes']} lane transcripts (skipped by token_report.py, so their spend is missing from its totals)")
    if rep["lower_bound"]:
        out.append("total is a lower bound" if own else "parity: not comparable, the token_report.py total is a lower bound")
    if rep.get("note"):
        out.append(f"note: {rep['note']}")
    if "drift_pct" in rep:
        out.append(f"parity: ccusage vs token_report.py {rep['drift_pct']:+.2f}% over the same window (day edges differ by timezone)")
    for label, rows in (("day", sp["days"]), ("project", sp["projects"][:rep["top"]]), ("model", sp["models"])):
        out.append(f"by {label}: " + ", ".join(f"{k} {tr._usd(u, miss)}" for k, u, miss in rows))
    out.append("by session (USD, unpriced last): " + ", ".join(f"{s['session'][:8]} {tr._usd(s['usd'], s['unpriced'])}" for s in rep["sessions"]))
    out.append(f"waste: {w['measured']} biggest sessions by USD measured ({w['spend_coverage']:.0%} of priced session spend), "
               f"{w['skipped_over_cap']} over {w['max_mb']} MB (main + lanes) not measured; lane (subagent) share of input-eq {w['subagent_share']:.1%}")
    out.append("savings levers (upper bounds of input-eq, not a bill; they overlap, so do not add them; state from user-level settings):")
    if w["already_set"]:
        out.append("  already set, skipped: " + ", ".join(w["already_set"]))
    out += [f"  {i}. {r['share']:.1%} {r['lever']}: {r['change']}" + (" [state unknown: user settings unreadable]" if r["state"] == "unknown" else "")
            for i, r in enumerate(w["levers"], 1)] or ["  no lever fires"]
    if w["exposure"]:
        e = w["exposure"]
        out.append(f"{e['kind']}: {e['share']:.1%} {e['lever']}: {e['change']}")
    return "\n".join(out)


def build(projects: str, since: datetime, top: int, limit: int, exe: str | None, max_bytes: int = tr.NUDGE_MAX_BYTES) -> dict:
    """Spend (ccusage when `exe` is set and its output parses, else token_report.py) plus the waste levers, as one dict."""
    roll = tr.build_rollup(projects, since, by="day", group="project")
    own = perun_spend(roll)
    cc = ccusage_spend(exe, since) if exe else None
    sessions = sorted(roll["sessions"], key=lambda r: (r["usd"] is None, -(r["usd"] or 0), -r["raw_tokens"], r["session"]))
    unreadable = {"sessions": roll["unreadable_sessions"], "lanes": roll["unreadable_lanes"]}
    rep = {"since": since.date().isoformat(), "top": top, "spend": cc or own, "unpriced": roll["unpriced_models"], "unreadable": unreadable,
           "lower_bound": bool(roll["unpriced_models"] or any(unreadable.values())),
           "sessions": [{"session": s["session"], "project": s["project"], "usd": s["usd"], "unpriced": s["unpriced_models"], "lanes": s["lanes"]}
                        for s in sessions[:top]],
           "waste": waste(sessions, projects, since, top, limit, max_bytes)}
    if exe and not cc:
        rep["note"] = "ccusage output was not the documented shape or it failed: used token_report.py"
    if cc and own["total_usd"] and not rep["lower_bound"]:
        rep["drift_pct"] = round((cc["total_usd"] - own["total_usd"]) / own["total_usd"] * 100, 2)
    return rep


def main(argv=None) -> int:
    """CLI entry: print the report (or --json). Returns 0, or 2 on a missing projects dir, an unparsable --since or a non-positive count."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--projects", metavar="DIR", help="projects dir (default: <claude config>/projects)")
    p.add_argument("--since", metavar="YYYY-MM-DD", help="local midnight start (default: 7 days ago)")
    p.add_argument("--sessions", type=int, default=20, metavar="N", help="biggest sessions to measure for waste (default 20)")
    p.add_argument("--top", type=int, default=5, metavar="N", help="rows per list and levers shown (default 5)")
    p.add_argument("--max-mb", type=int, default=tr.NUDGE_MAX_BYTES // 10**6, metavar="MB", help="skip transcripts over MB for the waste scan: build_report holds a whole file in memory (default %(default)s)")
    p.add_argument("--no-ccusage", action="store_true", help="use token_report.py even when ccusage is installed")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    home = tr.user_config_dir()
    projects = a.projects or (os.path.join(home, "projects") if home else "")
    since = tr.parse_timestamp(a.since, local=True) if a.since else \
        datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7)
    if not os.path.isdir(projects) or since is None or min(a.sessions, a.top, a.max_mb) < 1:
        print(f"spend_hub.py: need an existing projects dir ({projects or 'none resolved'}), a parsable --since and positive counts", file=sys.stderr)
        return 2
    exe = None if a.no_ccusage or a.projects or os.environ.get("CLAUDE_CONFIG_DIR") else shutil.which("ccusage")
    rep = build(projects, since, a.top, a.sessions, exe, a.max_mb * 10**6)
    print(json.dumps(rep, indent=2, sort_keys=True) if a.json else render(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
