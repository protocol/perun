#!/usr/bin/env python3
"""token_report.py — measure per-session token spend: main vs subagents.

WHY THIS EXISTS (the failure it closes)
----------------------------------------
"Token usage must be measured so it can be minimized" is a dead letter
without a tool that actually reads a session and says the numbers. Without
this, a conductor's only signal that a wave over-spent on orchestration
chatter instead of subagent execution is a vague feeling. This script reads
one Claude Code session transcript plus its subagent transcripts and prints
totals, a weighted cost proxy, and an orchestration-share flag — run it at
wave end and in the morning handoff (`SKILL.md` "Stay strategic").

HONESTY NOTE (read before quoting a number from this tool)
-------------------------------------------------------------
Every figure here is computed from the `usage` block the client already
logged in the transcript JSONL — input_tokens, cache_creation_input_tokens
(split into 5-minute / 1-hour cache writes), cache_read_input_tokens, and
output_tokens. This is NOT a bill: real invoiced price depends on the
model, the account's rate card, and pricing changes this tool does not
track. The "input-equivalent" figure applies the documented prompt-caching
MULTIPLIERS (cache read 0.1x, 5-minute cache write 1.25x, 1-hour cache
write 2x, both relative to base input price; output tokens are priced on a
separate, higher scale and are always reported separately, never folded
into input-equivalent) — see `docs/standards-index.md` ("Claude docs —
Prompt caching"). The "top 5 most expensive" ranking adds raw output
tokens on top of input-equivalent as a same-scale ranking proxy, not a
second currency — a useful ORDERING, not a price.

INPUT SHAPE (detected; a missing piece degrades to zero/unknown, never a
crash)
--------------------------------------------------------------------------
* Main transcript: `<session>.jsonl`, one JSON object per line. A line with
  `"type": "assistant"` and a `message.usage` object is a usage-bearing
  turn; every other line (user turns, meta lines, unparsable JSON) is
  skipped, not an error.
* A single logical turn can be logged as several consecutive lines sharing
  one `requestId` (one per streamed content block, `apiBlockIndex`
  0..N) — earlier blocks carry a partial usage snapshot, only the LAST
  block (highest `apiBlockIndex`) carries the turn's true totals. Summing
  every line as its own turn double- and triple-counts input/cache tokens;
  this tool groups by `requestId` and keeps only the max-`apiBlockIndex`
  line per group. A line with no `requestId` is treated as its own
  singleton turn (degrade path for an older/other transcript shape).
* Subagents: the sibling directory `<session>/subagents/*.jsonl` (one file
  per subagent). An optional sibling `<name>.meta.json` may carry
  `agentType` / `description` — used as the subagent's label when present;
  otherwise the label falls back to the file's stem and type "unknown".
* A subagent's "final message" (its handback size) is the `input.message`
  string of its last `SubagentHandback` tool call, by transcript order; if
  none was ever called (the agent stopped short), it falls back to the
  last plain `text` content block; if there is neither, it is `null` /
  `n/a` — never guessed.

WINDOWING
---------
`--since <ISO-8601>` keeps only turns at or after that timestamp, on both
main and every subagent; a subagent with zero turns in the window is
dropped from the report entirely (not printed as an all-zero row). A value
without a timezone is LOCAL time (what `date +%FT%T` prints); transcript
timestamps are UTC. Fractional seconds of any length, `Z`, `+00:00` and
`+0000` all parse (older Pythons reject some of these natively; a rejected
transcript timestamp used to drop its turn silently, so one window looked
empty while a nearby one did not). A turn with no parsable timestamp is
dropped under `--since` and counted without it. When a window is empty the
tool says so on stderr with the transcript's real time span.

LANES, MODELS, IN-FLIGHT
------------------------
Each turn's `message.model` is kept. A lane reports its majority model plus
counts (`models`), and a `by_model` totals map; `meta.json` `effort`, when
present, is shown (never guessed). The text report prints totals by model for
main and for all subagents. A lane with no `SubagentHandback` call and no
`stop_reason: end_turn` is `in_flight`: its spend still counts, so mid-session
numbers are not understated. `--top N` lists the N costliest lanes (default
5, 0 = all; JSON always carries every lane).

MAIN CONTEXT PER TURN
---------------------
Per main turn, context = input_tokens + cache_read. The report prints the
average, the first-third vs last-third averages (trend, needs >= 3 turns),
and flags `HANDOFF` when the last-third average (the average when < 3 turns)
exceeds 400000: write a handoff note and start a fresh session. JSON key:
`main_context`.

PRICING (--rates TSV)
---------------------
No prices ship with this tool. Pass your own rate card as a TSV, USD per 1M
tokens, one row per model, `#` comments and blank lines skipped:

  model<TAB>input<TAB>cache_write_5m<TAB>cache_write_1h<TAB>cache_read<TAB>output

A transcript model id matches the row whose model is its longest prefix
(`claude-x` prices `claude-x-20260101`). With `--rates`, the report prints
dollar cost for main, subagents and each listed lane; a model with no row is
named as UNPRICED and its tokens add nothing to the dollar figure (so the
figure is a floor). Without `--rates` the cost line reads `UNPRICED`. A bad
rates file exits 2. JSON: `cost_usd` (`null` without rates).

ORCHESTRATION SHARE
--------------------
`main_raw_tokens / (main_raw_tokens + subagents_raw_tokens)`, where
`raw_tokens` sums input + both cache-write splits + cache-read + output
(the same shape AWS's Well-Architected Agentic AI Lens uses for its
`AGENTCOST01-BP02` orchestration-to-execution diagnostic). A share above
20% is flagged — that page's stated ceiling: "Supervisors should consume
no more than 20% of total workflow tokens, leaving 80% for workers doing
execution." See `docs/standards-index.md`.

BUDGET GATE (--budget [TSV])
----------------------------
Turns the report into a pass/fail gate. Prints one line per breach, each
naming its lever, then exits 1; prints one `token budget: ok` line and exits
0 when every cap holds. Caps, their defaults, and the lever each names:

  max_orchestration_share  0.20       compact orchestrator (start a fresh
                                      session; the AWS ceiling quoted above)
  max_tool_calls           150        split lane (per lane)
  min_tool_calls           0 (off)    batch tasks (per lane; a thin lane pays
                                      the whole startup for little work; an
                                      unmeasured heuristic, opt in via TSV)
  max_input_equivalent     3000000    cap reads (per lane)
  max_startup_tokens       50000      trim brief (per lane; first-turn
                                      context = spawn prompt + auto-loaded
                                      files)

The defaults are STARTING VALUES to tune from your own `--json` output, not
claims about what a lane should cost. The three per-lane maxima sit near the
90th percentile of three local sessions measured with this tool on
2026-09-24 (tool calls p90 25-169, input-equivalent p90 0.28M-3.1M, startup
p90 29K-48K), so the gate flags outlier lanes rather than the median one.

Units differ on purpose: the orchestration share is computed on RAW tokens
(the AWS metric is a share of total workflow tokens), while the per-lane
token caps are INPUT-EQUIVALENT (cache-weighted, closer to cost). The
optional TSV overrides
them, one `<scope>\t<metric>\t<cap>` row per line (`#` comments and blank
lines skipped). Scope `*` sets the default for every lane; a subagent's file
stem or label sets that lane alone and wins over `*`. The orchestration
share takes scope `*` only. A malformed row, unknown metric, non-numeric or
non-finite cap, lane scope matching no lane, or missing TSV exits 2 (fail
closed; a gate with an unreadable budget never passes). So does
COULD_NOT_CHECK: zero usable main turns, or a subagent file with no usable
line (report mode warns about such a file on stderr instead of dropping it). A lane's tool calls are its unique `tool_use` block ids (the
same id on two streamed lines counts once), windowed by `--since`.

OUTPUT
------
Default text report is at most 20 lines (for up to a few models). `--json` prints the full computed
report (every subagent, not just the top 5) as one JSON object for
machine consumption.

CONTRACT (exit codes)
----------------------
* 0 — report printed (including an all-zero report; a transcript with no
  usage-bearing turns is a valid, if boring, answer).
* 1 — `--budget` only: at least one cap breached (one line per breach).
* 2 — the main session file does not exist / cannot be read, or a bad
  `--since` value was given, or a bad `--rates` file, or the budget TSV is unreadable or malformed
  (fail closed; never a guessed report).

USAGE
-----
  token_report.py --session <path/to/session.jsonl> [--since ISO] [--json] [--top N] [--rates TSV]
  token_report.py --session <path/to/session.jsonl> [--since ISO] --budget [budget.tsv]
  token_report.py --selftest
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone

OK = 0
BREACH = 1
ERROR = 2

CACHE_READ_MULT = 0.1
CACHE_WRITE_5M_MULT = 1.25
CACHE_WRITE_1H_MULT = 2.0
ORCHESTRATION_FLAG_THRESHOLD = 0.20
CONTEXT_HANDOFF_THRESHOLD = 400_000

# metric -> (default cap, lever). Order is the breach-line order within a lane.
# Starting values to tune from --json output, not claims (see BUDGET GATE).
BUDGET_METRICS = {
    "max_tool_calls": (150, "split lane: dispatch narrower lanes, each with its own tool-call cap"),
    "min_tool_calls": (0, "batch tasks: fold related tasks into one lane to amortize startup"),
    "max_input_equivalent": (3_000_000, "cap reads: read ranges and grep hits, not whole files"),
    "max_startup_tokens": (50_000, "trim brief: shorter spawn prompt, fewer auto-loaded files"),
}
ORCHESTRATION_LEVER = "compact orchestrator: start a fresh session (beats /compact per SKILL)"
DEFAULT_BUDGET = {
    "orchestration": ORCHESTRATION_FLAG_THRESHOLD,
    "star": {m: cap for m, (cap, _lever) in BUDGET_METRICS.items()},
    "lanes": {},
}

ZERO_USAGE = {
    "input_tokens": 0,
    "cache_write_5m": 0,
    "cache_write_1h": 0,
    "cache_read": 0,
    "output_tokens": 0,
}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def read_jsonl(path: str):
    """Yield parsed dicts from a JSONL file; silently skip unparsable lines."""
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(obj, dict):
                yield obj


def parse_timestamp(value, local=False):
    """Parse an ISO-8601 timestamp (Z, +HH:MM, +HHMM, any fraction length). None on failure.

    A value with no timezone is UTC, or the machine's local zone when `local`
    (used for the user-typed --since).
    """
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    text = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", text)
    text = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], text, count=1)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone() if local else dt.replace(tzinfo=timezone.utc)
    return dt


def _turn_usage(entry: dict) -> dict:
    """Extract the flat usage shape this tool works in from one assistant entry."""
    usage = (entry.get("message") or {}).get("usage") or {}
    cache_creation = usage.get("cache_creation") or {}
    w5 = cache_creation.get("ephemeral_5m_input_tokens") or 0
    w1 = cache_creation.get("ephemeral_1h_input_tokens") or 0
    # A turn may log only the total: attribute any unsplit remainder to 5m writes.
    w5 += max(0, (usage.get("cache_creation_input_tokens") or 0) - w5 - w1)
    return {
        "input_tokens": usage.get("input_tokens") or 0,
        "cache_write_5m": w5,
        "cache_write_1h": w1,
        "cache_read": usage.get("cache_read_input_tokens") or 0,
        "output_tokens": usage.get("output_tokens") or 0,
    }


def extract_turns(entries: list) -> list:
    """Dedupe multi-block turns (same requestId, keep max apiBlockIndex), sorted by timestamp.

    A line with no usable requestId is its own singleton turn (degrade path).
    """
    grouped: dict = {}
    singleton_key = 0
    order: list = []
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        usage = (entry.get("message") or {}).get("usage")
        if not usage:
            continue
        request_id = entry.get("requestId")
        block_index = entry.get("apiBlockIndex")
        ts = parse_timestamp(entry.get("timestamp"))
        if isinstance(request_id, str) and request_id:
            key = ("req", request_id)
        else:
            singleton_key += 1
            key = ("single", singleton_key)
        rank = block_index if isinstance(block_index, int) else 0
        existing = grouped.get(key)
        if existing is None or rank >= existing["_rank"]:
            grouped[key] = {"_rank": rank, "timestamp": ts, "model": (entry.get("message") or {}).get("model"),
                            **_turn_usage(entry)}
        if key not in order:
            order.append(key)
    turns = [grouped[k] for k in order]
    turns.sort(key=lambda t: (t["timestamp"] is None, t["timestamp"] or datetime.min.replace(tzinfo=timezone.utc)))
    for t in turns:
        t.pop("_rank", None)
    return turns


def filter_since(turns: list, since):
    if since is None:
        return turns
    return [t for t in turns if t["timestamp"] is not None and t["timestamp"] >= since]


def sum_turns(turns: list) -> dict:
    totals = dict(ZERO_USAGE)
    for t in turns:
        for k in ZERO_USAGE:
            totals[k] += t.get(k, 0)
    totals["input_equivalent"] = round(
        totals["input_tokens"]
        + totals["cache_write_5m"] * CACHE_WRITE_5M_MULT
        + totals["cache_write_1h"] * CACHE_WRITE_1H_MULT
        + totals["cache_read"] * CACHE_READ_MULT,
        2,
    )
    totals["raw_tokens"] = (
        totals["input_tokens"]
        + totals["cache_write_5m"]
        + totals["cache_write_1h"]
        + totals["cache_read"]
        + totals["output_tokens"]
    )
    return totals


def model_stats(turns: list):
    """(majority model, {model: turn count}, {model: totals}); the synthetic placeholder model is ignored."""
    names = [t.get("model") for t in turns if t.get("model") and t["model"] != "<synthetic>"]
    counts = dict(Counter(names).most_common())
    by_model = {m: sum_turns([t for t in turns if t.get("model") == m]) for m in counts}
    return (next(iter(counts), None), counts, by_model)


def load_rates(path: str) -> dict:
    """Parse `model<TAB>input<TAB>cache_write_5m<TAB>cache_write_1h<TAB>cache_read<TAB>output` (USD per 1M tokens).

    Raises ValueError on a malformed row or a non-finite/negative price, OSError if unreadable.
    """
    rates = {}
    with open(path, "r", encoding="utf-8") as fh:
        for n, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            cols = [c.strip() for c in line.split("\t")]
            if len(cols) != 6:
                raise ValueError(f"line {n}: want model + 5 prices (tab separated): {line!r}")
            try:
                prices = [float(c) for c in cols[1:]]
            except ValueError:
                raise ValueError(f"line {n}: price is not a number: {line!r}") from None
            if not all(math.isfinite(x) and x >= 0 for x in prices):
                raise ValueError(f"line {n}: price is not a finite non-negative number: {line!r}")
            rates[cols[0]] = dict(zip(("input_tokens", "cache_write_5m", "cache_write_1h", "cache_read", "output_tokens"), prices))
    return rates


def price(by_model: dict, rates):
    """(USD, [unpriced models]) for a {model: totals} map; (None, []) without rates. Unpriced models add 0."""
    if rates is None:
        return (None, [])
    usd, missing = 0.0, []
    for model, tot in by_model.items():
        match = max((k for k in rates if str(model).startswith(k)), key=len, default=None)
        if match is None:
            missing.append(model)
            continue
        usd += sum(tot[k] * v for k, v in rates[match].items()) / 1e6
    return (round(usd, 4), missing)


def merge_by_model(maps: list) -> dict:
    out: dict = {}
    for mp in maps:
        for model, tot in mp.items():
            out.setdefault(model, []).append(tot)
    return {m: sum_turns(ts) for m, ts in out.items()}


def main_context(turns: list) -> dict:
    """Average input+cache_read per main turn, first/last-third trend, handoff flag."""
    ctx = [t["input_tokens"] + t["cache_read"] for t in turns]
    if not ctx:
        return {"avg": 0, "first_third": None, "last_third": None, "handoff": False,
                "threshold": CONTEXT_HANDOFF_THRESHOLD}

    def avg(xs):
        return round(sum(xs) / len(xs))

    k = len(ctx) // 3
    first, last = (avg(ctx[:k]), avg(ctx[-k:])) if k else (None, None)
    return {"avg": avg(ctx), "first_third": first, "last_third": last,
            "handoff": (last if last is not None else avg(ctx)) > CONTEXT_HANDOFF_THRESHOLD,
            "threshold": CONTEXT_HANDOFF_THRESHOLD}


def weighted_tokens(totals: dict) -> float:
    """The one token measure (input-equivalent + output) every tokens-per-PR figure uses; never raw_tokens."""
    return totals["input_equivalent"] + totals["output_tokens"]


def report_weighted_tokens(report: dict) -> float:
    """weighted_tokens for a build_report() result: main session plus its subagents."""
    return weighted_tokens(report["main"]) + weighted_tokens(report["subagents_totals"])


def pr_count(since, repo="."):
    """Distinct `Merge pull request #N` first-parent merges in `repo` since `since` (datetime); None if git fails."""
    r = subprocess.run(["git", "-C", repo, "log", "--first-parent", f"--since={since.isoformat()}", "--format=%s"],
                       capture_output=True, text=True)
    if r.returncode:
        return None
    return len({m.group(1) for ln in r.stdout.splitlines() if (m := re.match(r"^Merge pull request #(\d+)\b", ln))})


def extract_handback_chars(entries: list):
    """Last SubagentHandback message length; else last text block length; else None."""
    last_handback = None
    last_text = None
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        for block in (entry.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "SubagentHandback":
                message = (block.get("input") or {}).get("message")
                if isinstance(message, str):
                    last_handback = len(message)
            elif block.get("type") == "text" and isinstance(block.get("text"), str):
                last_text = len(block["text"])
    return last_handback if last_handback is not None else last_text


def extract_tool_calls(entries: list, since) -> int:
    """Count unique tool_use block ids on assistant lines at/after `since` (None = all).

    A streamed turn can repeat a block on several lines; the id dedupes it.
    A tool_use block with no id counts once per line (degrade path).
    """
    seen: set = set()
    anonymous = 0
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        if since is not None:
            ts = parse_timestamp(entry.get("timestamp"))
            if ts is None or ts < since:
                continue
        for block in (entry.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                if isinstance(block.get("id"), str) and block["id"]:
                    seen.add(block["id"])
                else:
                    anonymous += 1
    return len(seen) + anonymous


def load_meta(jsonl_path: str) -> dict:
    meta_path = jsonl_path[: -len(".jsonl")] + ".meta.json" if jsonl_path.endswith(".jsonl") else jsonl_path + ".meta.json"
    if not os.path.isfile(meta_path):
        return {}
    try:
        with open(meta_path, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
    except (json.JSONDecodeError, ValueError, OSError):
        return {}
    return obj if isinstance(obj, dict) else {}


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def build_subagent_report(jsonl_path: str, since) -> dict:
    """One lane's totals; None when windowed out; {"unusable": True, ...} when no usable turn at all."""
    entries = list(read_jsonl(jsonl_path))
    stem = os.path.basename(jsonl_path)
    if stem.endswith(".jsonl"):
        stem = stem[: -len(".jsonl")]
    all_turns = extract_turns(entries)
    if not all_turns:
        return {"file": stem, "unusable": True}
    turns = filter_since(all_turns, since)
    if not turns:
        return None
    meta = load_meta(jsonl_path)
    model, models, by_model = model_stats(turns)
    asst = [e for e in entries if e.get("type") == "assistant"]
    last_stop = (asst[-1].get("message") or {}).get("stop_reason") if asst else None
    called = any(b.get("name") == "SubagentHandback" for e in asst
                 for b in (e.get("message") or {}).get("content") or []
                 if isinstance(b, dict) and b.get("type") == "tool_use")
    first = turns[0]
    startup = first["input_tokens"] + first["cache_write_5m"] + first["cache_write_1h"] + first["cache_read"]
    totals = sum_turns(turns)
    return {
        "label": meta.get("description") or stem,
        "agent_type": meta.get("agentType", "unknown"),
        "file": stem,
        "startup_tokens": startup,
        "handback_chars": extract_handback_chars(entries),
        "tool_calls": extract_tool_calls(entries, since),
        "model": model,
        "models": models,
        "by_model": by_model,
        "effort": meta.get("effort"),
        "in_flight": not called and last_stop != "end_turn",
        **totals,
    }


def build_report(session_path: str, since, top: int = 5, rates=None) -> dict:
    main_entries = list(read_jsonl(session_path))
    all_main = extract_turns(main_entries)
    main_turns = filter_since(all_main, since)
    stamps = [t["timestamp"] for t in all_main if t["timestamp"]]
    main_totals = sum_turns(main_turns)

    session_dir = session_path[: -len(".jsonl")] if session_path.endswith(".jsonl") else session_path
    subagents_dir = os.path.join(session_dir, "subagents")
    subagents = []
    unusable = []
    if os.path.isdir(subagents_dir):
        for name in sorted(os.listdir(subagents_dir)):
            if not name.endswith(".jsonl"):
                continue
            rec = build_subagent_report(os.path.join(subagents_dir, name), since)
            if rec is not None and rec.get("unusable"):
                unusable.append(rec["file"])
            elif rec is not None:
                subagents.append(rec)

    sub_raw = sum(s["raw_tokens"] for s in subagents)
    sub_input_eq = sum(s["input_equivalent"] for s in subagents)
    sub_output = sum(s["output_tokens"] for s in subagents)
    denom = main_totals["raw_tokens"] + sub_raw
    share = (main_totals["raw_tokens"] / denom) if denom else 0.0

    ranked = sorted(subagents, key=lambda s: s["input_equivalent"] + s["output_tokens"], reverse=True)
    top5 = ranked[:top] if top > 0 else ranked
    _m, main_models, main_by_model = model_stats(main_turns)
    sub_by_model = merge_by_model([s["by_model"] for s in subagents])
    cost = {"main": price(main_by_model, rates), "subagents": price(sub_by_model, rates)}
    for s in subagents:
        s["cost_usd"], s["unpriced_models"] = price(s["by_model"], rates)

    return {
        "session": session_path,
        "since": since.isoformat() if since else None,
        "main": main_totals,
        "main_turns": len(main_turns),
        "main_span": [stamps[0].isoformat(), stamps[-1].isoformat()] if stamps else None,
        "main_context": main_context(main_turns),
        "main_models": main_models,
        "main_by_model": main_by_model,
        "subagents_by_model": sub_by_model,
        "cost_usd": None if rates is None else {
            "main": cost["main"][0], "subagents": cost["subagents"][0],
            "total": round(cost["main"][0] + cost["subagents"][0], 4),
            "unpriced_models": sorted(set(cost["main"][1] + cost["subagents"][1]))},
        "unusable_subagents": unusable,
        "subagents_count": len(subagents),
        "subagents_totals": {
            "input_equivalent": round(sub_input_eq, 2),
            "output_tokens": sub_output,
            "raw_tokens": sub_raw,
        },
        "orchestration_share": round(share, 4),
        "orchestration_flag": share > ORCHESTRATION_FLAG_THRESHOLD,
        "top_subagents": top5,
        "all_subagents": subagents,
    }


# ---------------------------------------------------------------------------
# Budget gate
# ---------------------------------------------------------------------------


def load_budget(path: str) -> dict:
    """Parse a `<scope>\t<metric>\t<cap>` TSV over DEFAULT_BUDGET.

    Raises ValueError (with the offending line) on a malformed row, unknown
    metric, non-numeric or negative cap, or an orchestration row whose scope
    is not `*`; OSError on an unreadable file. The caller fails closed.
    """
    budget = {"orchestration": DEFAULT_BUDGET["orchestration"],
              "star": dict(DEFAULT_BUDGET["star"]), "lanes": {}}
    with open(path, "r", encoding="utf-8") as fh:
        for n, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            cols = [c.strip() for c in line.split("\t")]
            if len(cols) != 3:
                raise ValueError(f"line {n}: want <scope><TAB><metric><TAB><cap>: {line!r}")
            scope, metric, cap_text = cols
            try:
                cap = float(cap_text)
            except ValueError:
                raise ValueError(f"line {n}: cap is not a number: {cap_text!r}") from None
            if not math.isfinite(cap):
                raise ValueError(f"line {n}: cap is not finite: {cap_text!r}")
            if cap < 0:
                raise ValueError(f"line {n}: cap is negative: {cap_text!r}")
            if metric == "max_orchestration_share":
                if scope != "*":
                    raise ValueError(f"line {n}: max_orchestration_share takes scope '*' only")
                budget["orchestration"] = cap
            elif metric not in BUDGET_METRICS:
                raise ValueError(f"line {n}: unknown metric: {metric!r}")
            elif scope == "*":
                budget["star"][metric] = cap
            else:
                budget["lanes"].setdefault(scope, {})[metric] = cap
    return budget


def could_not_check(report: dict, budget: dict) -> list:
    """Reasons the gate cannot give a verdict; any entry means exit 2, never a pass.

    Zero usable main turns (share undefined), a subagent file with no usable
    line, or a lane-scope TSV row that matches no lane's file stem or label.
    """
    reasons = []
    if report["main_turns"] == 0:
        reasons.append("main transcript has no usable turns (orchestration share undefined)")
    for stem in report["unusable_subagents"]:
        reasons.append(f"subagent file {stem}.jsonl has no usable turns")
    names = {s["file"] for s in report["all_subagents"]} | {s["label"] for s in report["all_subagents"]}
    for scope, caps in sorted(budget["lanes"].items()):
        if scope not in names:
            reasons.append(f"budget row scope {scope!r} ({', '.join(sorted(caps))}) matches no lane")
    return reasons


def _num(value) -> str:
    """Render 3001000.0 as 3001000 and 0.2 as 0.2 — breach lines stay exact and short."""
    return str(int(value)) if float(value).is_integer() else str(value)


def check_budget(report: dict, budget: dict) -> list:
    """Return one breach line per exceeded cap: orchestrator first, then lanes by file.

    Pure and deterministic: same report + budget, same lines in the same order.
    """
    lines = []
    share, ceiling = report["orchestration_share"], budget["orchestration"]
    if share > ceiling:
        lines.append(f"BREACH orchestrator max_orchestration_share={_num(share)} > {_num(ceiling)}"
                     f" -> {ORCHESTRATION_LEVER}")
    source = {"max_tool_calls": "tool_calls", "min_tool_calls": "tool_calls",
              "max_input_equivalent": "input_equivalent", "max_startup_tokens": "startup_tokens"}
    for lane in sorted(report["all_subagents"], key=lambda s: s["file"]):
        caps = dict(budget["star"])
        caps.update(budget["lanes"].get(lane["label"], {}))
        caps.update(budget["lanes"].get(lane["file"], {}))
        for metric, (_default, lever) in BUDGET_METRICS.items():
            value, cap = lane[source[metric]], caps[metric]
            is_floor = metric.startswith("min_")
            if (value < cap) if is_floor else (value > cap):
                op = "<" if is_floor else ">"
                lines.append(f"BREACH lane={lane['file']} {metric}={_num(value)} {op} {_num(cap)} -> {lever}")
    return lines


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _usd(x) -> str:
    return f"${x:.2f}"


def _model_line(label: str, by_model: dict) -> str:
    parts = [f"{m} raw={t['raw_tokens']} out={t['output_tokens']}" for m, t in by_model.items()]
    return f"{label} by model: " + ("; ".join(parts) or "n/a")


def render_text(report: dict) -> str:
    lines = []
    lines.append(f"Token report — {os.path.basename(report['session'])}"
                 + (f" (since {report['since']})" if report["since"] else ""))
    m = report["main"]
    lines.append(f"MAIN       in={m['input_tokens']} cacheW5m={m['cache_write_5m']} "
                 f"cacheW1h={m['cache_write_1h']} cacheR={m['cache_read']} out={m['output_tokens']} "
                 f"input-eq={m['input_equivalent']}")
    st = report["subagents_totals"]
    lines.append(f"SUBAGENTS(n={report['subagents_count']}) input-eq={st['input_equivalent']} "
                 f"out={st['output_tokens']} raw={st['raw_tokens']}")
    lines.append(_model_line("MAIN", report["main_by_model"]))
    lines.append(_model_line("SUBAGENTS", report["subagents_by_model"]))
    c = report["cost_usd"]
    if c is None:
        lines.append("Cost: UNPRICED (pass --rates TSV)")
    else:
        miss = f" UNPRICED models: {', '.join(c['unpriced_models'])}" if c["unpriced_models"] else ""
        lines.append(f"Cost: main {_usd(c['main'])} subagents {_usd(c['subagents'])} total {_usd(c['total'])}{miss}")
    x = report["main_context"]
    if report["main_turns"]:
        trend = f" first-third={x['first_third']} last-third={x['last_third']}" if x["first_third"] is not None else ""
        hand = f"  <-- HANDOFF >{x['threshold']}: write a handoff note and start fresh" if x["handoff"] else ""
        lines.append(f"Main context/turn (input+cacheR): avg={x['avg']}{trend}{hand}")
    flag = "  <-- FLAG >20%" if report["orchestration_flag"] else ""
    lines.append(f"Orchestration share (main/(main+subagents)): {report['orchestration_share'] * 100:.1f}%{flag}")
    if report["orchestration_flag"]:
        hint = "Cheaper route: run main on a cheaper tier for routine turns"
        if m["raw_tokens"] and m["cache_read"] * 2 > m["raw_tokens"]:
            hint += "; main cache reads dominate, start a fresh session from a handoff note"
        lines.append(hint)
    if report["top_subagents"]:
        lines.append("Top subagents by cost (input-eq + output):")
        for i, s in enumerate(report["top_subagents"], 1):
            cost = round(s["input_equivalent"] + s["output_tokens"], 2)
            handback = s["handback_chars"] if s["handback_chars"] is not None else "n/a"
            mdl = ",".join(f"{k}:{v}" for k, v in s["models"].items()) or "n/a"
            effort = f" effort={s['effort']}" if s.get("effort") else ""
            usd = "" if s.get("cost_usd") is None else f" usd={_usd(s['cost_usd'])}"
            fly = " in-flight" if s["in_flight"] else ""
            lines.append(f"  {i}. {s['label']} [{s['agent_type']}] model={mdl}{effort}{usd} cost={cost} "
                         f"startup={s['startup_tokens']} calls={s['tool_calls']} out={s['output_tokens']} "
                         f"handback_chars={handback}{fly}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--session", help="path to <session>.jsonl")
    p.add_argument("--since", help="ISO-8601 timestamp; only turns at/after it are counted")
    p.add_argument("--json", action="store_true", help="print the full report as JSON")
    p.add_argument("--budget", nargs="?", const="", metavar="TSV",
                   help="gate mode: exit 1 with one line per breached cap (optional TSV overrides defaults)")
    p.add_argument("--top", type=int, default=5, metavar="N", help="lanes to list (default 5, 0 = all)")
    p.add_argument("--rates", metavar="TSV", help="user-supplied USD-per-1M rates; without it cost is UNPRICED")
    p.add_argument("--selftest", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return _selftest()

    if not args.session:
        print("token_report.py: --session <path> is required", file=sys.stderr)
        return ERROR
    if not os.path.isfile(args.session):
        print(f"token_report.py: session file not found: {args.session}", file=sys.stderr)
        return ERROR

    since = None
    if args.since:
        since = parse_timestamp(args.since, local=True)
        if since is None:
            print(f"token_report.py: could not parse --since value: {args.since}", file=sys.stderr)
            return ERROR

    rates = None
    if args.rates:
        try:
            rates = load_rates(args.rates)
        except (OSError, ValueError) as exc:
            print(f"token_report.py: bad --rates file {args.rates}: {exc}", file=sys.stderr)
            return ERROR
    report = build_report(args.session, since, max(args.top, 0), rates)
    if since and not report["main_turns"] and not report["subagents_count"]:
        print(f"token_report.py: warning: --since {since.isoformat()} matched no turns; "
              f"main transcript spans {report['main_span']}", file=sys.stderr)
    if args.budget is not None:
        try:
            budget = load_budget(args.budget) if args.budget else DEFAULT_BUDGET
        except (OSError, ValueError) as exc:
            print(f"token_report.py: bad --budget file {args.budget}: {exc}", file=sys.stderr)
            return ERROR
        reasons = could_not_check(report, budget)
        if reasons:
            for reason in reasons:
                print(f"COULD_NOT_CHECK: {reason}", file=sys.stderr)
            return ERROR
        breaches = check_budget(report, budget)
        if not breaches:
            print(f"token budget: ok ({report['subagents_count']} lanes, "
                  f"orchestration share {report['orchestration_share'] * 100:.1f}%)")
            return OK
        print("\n".join(breaches))
        return BREACH
    for stem in report["unusable_subagents"]:
        print(f"token_report.py: warning: subagent file {stem}.jsonl has no usable turns", file=sys.stderr)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return OK


# ---------------------------------------------------------------------------
# Selftest: committed fixtures (fixtures/token/) for the full-shape happy
# path, plus small in-memory/temp-file cases for edge branches (missing
# file, missing subagents dir, requestId-less degrade, since-window,
# orchestration flag firing). Fully offline, synthetic data only — never a
# real transcript.
# ---------------------------------------------------------------------------


def _selftest() -> int:
    import tempfile

    failures: list = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        if not cond:
            failures.append(f"{label}: {detail}")

    here = os.path.dirname(os.path.abspath(__file__))
    fixture_session = os.path.join(here, "fixtures", "token", "session.jsonl")

    # -- full-shape happy path against committed fixtures --------------------
    report = build_report(fixture_session, None)
    m = report["main"]
    check("main-input", m["input_tokens"] == 190, str(m))
    check("main-cache-write-5m", m["cache_write_5m"] == 200, str(m))
    check("main-cache-write-1h", m["cache_write_1h"] == 0, str(m))
    check("main-cache-read", m["cache_read"] == 115, str(m))
    check("main-output", m["output_tokens"] == 170, str(m))
    check("main-input-eq", m["input_equivalent"] == 451.5, str(m))
    # main-output above is the real dedup proof: 30+5+40+100=175 if the
    # partial r2 block (output=5) were wrongly summed alongside its final
    # block (output=40) instead of being superseded by it.
    check("subagents-count", report["subagents_count"] == 2, str(report["subagents_count"]))

    by_label = {s["file"]: s for s in report["all_subagents"]}
    alpha = by_label["agent-alpha"]
    beta = by_label["agent-beta"]
    check("alpha-meta-label", alpha["label"] == "Fictional fixture task: build widget X", alpha["label"])
    check("alpha-agent-type", alpha["agent_type"] == "caveman-lane", alpha["agent_type"])
    check("alpha-startup", alpha["startup_tokens"] == 5 + 1000 + 0 + 0, str(alpha))
    check("alpha-input-eq", alpha["input_equivalent"] == round(7 + 1000 * 1.25 + 1500 * 0.1, 2), str(alpha))
    check("alpha-output", alpha["output_tokens"] == 320, str(alpha))
    check("alpha-handback-chars", alpha["handback_chars"] == len("DONE short handback"), str(alpha))

    check("beta-no-meta-falls-back-to-filename", beta["label"] == "agent-beta", beta["label"])
    check("beta-agent-type-unknown", beta["agent_type"] == "unknown", beta["agent_type"])
    check("beta-startup", beta["startup_tokens"] == 1000 + 0 + 5000 + 0, str(beta))
    check("beta-input-eq", beta["input_equivalent"] == round(1000 + 5000 * 2.0, 2), str(beta))
    check("beta-no-handback-falls-back-to-last-text",
          beta["handback_chars"] == len("ran out of budget, stopped without a handback call"),
          str(beta))

    check("top-subagents-ranked-most-expensive-first",
          report["top_subagents"][0]["file"] == "agent-beta", [s["file"] for s in report["top_subagents"]])
    check("orchestration-share-not-flagged-when-subagents-dominate",
          report["orchestration_flag"] is False, str(report["orchestration_share"]))

    text = render_text(report)
    check("text-report-at-most-20-lines", len(text.splitlines()) <= 20, str(len(text.splitlines())))
    check("text-report-mentions-both-subagents", "agent-beta" in text or "1000" in text, text)

    # -- --since windowing: drops turns and subagents outside the window -----
    since_cut = parse_timestamp("2026-01-01T00:30:00Z")
    windowed = build_report(fixture_session, since_cut)
    check("since-drops-early-main-turns", windowed["main"]["input_tokens"] == 10, str(windowed["main"]))
    check("since-drops-all-subagents-before-cutoff", windowed["subagents_count"] == 0, str(windowed["subagents_count"]))

    # -- missing session file: exit 2, not a crash ----------------------------
    rc_missing = main(["--session", os.path.join(here, "fixtures", "token", "does-not-exist.jsonl")])
    check("missing-session-file-exits-2", rc_missing == ERROR, str(rc_missing))

    # -- bad --since value: exit 2 -------------------------------------------
    rc_bad_since = main(["--session", fixture_session, "--since", "not-a-date"])
    check("bad-since-exits-2", rc_bad_since == ERROR, str(rc_bad_since))

    with tempfile.TemporaryDirectory() as tmp:
        # -- no sibling subagents dir at all: degrades to 0 subagents --------
        lone = os.path.join(tmp, "lone.jsonl")
        with open(lone, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "type": "assistant", "timestamp": "2026-01-01T00:00:00Z",
                "requestId": "x1", "apiBlockIndex": 0,
                "message": {"usage": {"input_tokens": 3, "output_tokens": 4}},
            }) + "\n")
        lone_report = build_report(lone, None)
        check("no-subagents-dir-degrades-to-zero", lone_report["subagents_count"] == 0, str(lone_report))
        check("missing-cache-fields-default-zero", lone_report["main"]["cache_write_5m"] == 0, str(lone_report))

        # -- requestId-less lines: no dedup collapse, each line its own turn -
        no_req = os.path.join(tmp, "noreq.jsonl")
        with open(no_req, "w", encoding="utf-8") as fh:
            for i in range(2):
                fh.write(json.dumps({
                    "type": "assistant", "timestamp": f"2026-01-01T00:0{i}:00Z",
                    "message": {"usage": {"input_tokens": 10, "output_tokens": 1}},
                }) + "\n")
        no_req_report = build_report(no_req, None)
        check("no-requestid-sums-every-line", no_req_report["main"]["input_tokens"] == 20,
              str(no_req_report["main"]))

        # -- orchestration flag fires when main dominates the token volume ---
        heavy_main = os.path.join(tmp, "heavy.jsonl")
        with open(heavy_main, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "type": "assistant", "timestamp": "2026-01-01T00:00:00Z",
                "requestId": "h1", "apiBlockIndex": 0,
                "message": {"usage": {"input_tokens": 10000, "output_tokens": 100}},
            }) + "\n")
        heavy_dir = os.path.join(tmp, "heavy", "subagents")
        os.makedirs(heavy_dir)
        with open(os.path.join(heavy_dir, "agent-tiny.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "type": "assistant", "timestamp": "2026-01-01T00:01:00Z",
                "requestId": "h2", "apiBlockIndex": 0,
                "message": {"usage": {"input_tokens": 10, "output_tokens": 1}},
            }) + "\n")
        heavy_report = build_report(heavy_main, None)
        check("orchestration-flag-fires-when-main-dominates",
              heavy_report["orchestration_flag"] is True, str(heavy_report["orchestration_share"]))

        # -- malformed-only file: zero turns, not a crash --------------------
        garbage = os.path.join(tmp, "garbage.jsonl")
        with open(garbage, "w", encoding="utf-8") as fh:
            fh.write("{not json,,,\n{also not json\n")
        garbage_report = build_report(garbage, None)
        check("malformed-lines-degrade-to-zero-turns", garbage_report["main"]["raw_tokens"] == 0,
              str(garbage_report["main"]))

    # Unsplit cache writes (only cache_creation_input_tokens logged) count as 5m writes.
    u = _turn_usage({"message": {"usage": {"input_tokens": 1, "cache_creation_input_tokens": 1000,
                                           "cache_read_input_tokens": 0, "output_tokens": 1}}})
    check("unsplit cache_creation_input_tokens -> 5m writes", u["cache_write_5m"] == 1000 and u["cache_write_1h"] == 0, str(u))
    u2 = _turn_usage({"message": {"usage": {"cache_creation_input_tokens": 1000,
                                            "cache_creation": {"ephemeral_1h_input_tokens": 400}}}})
    check("partial split: remainder -> 5m", u2["cache_write_5m"] == 600 and u2["cache_write_1h"] == 400, str(u2))

    # -- budget gate (--budget): synthetic lanes, each built to trip one cap --
    import contextlib
    import io

    def quiet_main(argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(argv)

    def turn(req, ts, usage, tools=()):
        content = [{"type": "tool_use", "id": t, "name": "Bash", "input": {}} for t in tools]
        return json.dumps({"type": "assistant", "timestamp": ts, "requestId": req,
                           "apiBlockIndex": 0, "message": {"usage": usage, "content": content}}) + "\n"

    with tempfile.TemporaryDirectory() as tmp:
        sess = os.path.join(tmp, "s.jsonl")
        with open(sess, "w", encoding="utf-8") as fh:
            fh.write(turn("m1", "2026-01-01T00:00:00Z", {"input_tokens": 100, "output_tokens": 10}))
        sub = os.path.join(tmp, "s", "subagents")
        os.makedirs(sub)
        with open(os.path.join(sub, "agent-ok.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(turn("o1", "2026-01-01T00:01:00Z", {"input_tokens": 1000, "output_tokens": 10},
                          [f"t{i}" for i in range(6)]))
        report_ok = build_report(sess, None)
        check("tool-calls-counted", report_ok["all_subagents"][0]["tool_calls"] == 6, str(report_ok["all_subagents"]))
        check("default-budget-clean-run-has-no-breach", check_budget(report_ok, dict(DEFAULT_BUDGET)) == [],
              str(check_budget(report_ok, dict(DEFAULT_BUDGET))))
        check("budget-clean-run-exits-0", quiet_main(["--session", sess, "--budget"]) == OK, "")

        with open(os.path.join(sub, "agent-wide.jsonl"), "w", encoding="utf-8") as fh:
            # Same tool_use id logged on two streamed lines counts once: 6 calls, not 7.
            fh.write(turn("w1", "2026-01-01T00:02:00Z", {"input_tokens": 1000, "output_tokens": 1}, ["a", "b"]))
            fh.write(turn("w2", "2026-01-01T00:03:00Z", {"input_tokens": 3000000, "output_tokens": 1},
                          ["b", "c", "d", "e", "f"]))
        with open(os.path.join(sub, "agent-thin.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(turn("t1", "2026-01-01T00:04:00Z", {"input_tokens": 60000, "output_tokens": 1}, ["x"]))
        with open(sess, "a", encoding="utf-8") as fh:
            fh.write(turn("m2", "2026-01-01T00:05:00Z", {"input_tokens": 2000000, "output_tokens": 1}))
        report_bad = build_report(sess, None)
        wide = {s["file"]: s for s in report_bad["all_subagents"]}["agent-wide"]
        check("duplicate-tool-use-id-counted-once", wide["tool_calls"] == 6, str(wide["tool_calls"]))

        tsv = os.path.join(tmp, "budget.tsv")
        with open(tsv, "w", encoding="utf-8") as fh:
            fh.write("# scope\tmetric\tcap\n*\tmax_tool_calls\t150\n*\tmin_tool_calls\t5\n"
                     "agent-wide\tmax_tool_calls\t5\n")
        budget = load_budget(tsv)
        check("lane-row-overrides-star-row", budget["lanes"]["agent-wide"]["max_tool_calls"] == 5, str(budget))
        breaches = check_budget(report_bad, budget)
        expected = [
            "BREACH orchestrator max_orchestration_share=0.3951 > 0.2 -> compact orchestrator",
            "BREACH lane=agent-thin min_tool_calls=1 < 5 -> batch tasks",
            "BREACH lane=agent-thin max_startup_tokens=60000 > 50000 -> trim brief",
            "BREACH lane=agent-wide max_tool_calls=6 > 5 -> split lane",
            "BREACH lane=agent-wide max_input_equivalent=3001000 > 3000000 -> cap reads",
        ]
        got = [b.split(":", 1)[0] for b in breaches]
        check("one-line-per-breach-naming-the-lever", got == expected, "\n".join(breaches))
        check("breach-run-exits-1", quiet_main(["--session", sess, "--budget", tsv]) == BREACH, "")
        check("orchestration-lever-says-fresh-session", "start a fresh session" in breaches[0], breaches[0])
        check("min-tool-calls-heuristic-off-by-default", DEFAULT_BUDGET["star"]["min_tool_calls"] == 0
              and not any("min_tool_calls" in b for b in check_budget(report_bad, DEFAULT_BUDGET)),
              str(check_budget(report_bad, DEFAULT_BUDGET)))

        # A lane-scope row that matches no lane is a typo, not a silent no-op.
        with open(tsv, "w", encoding="utf-8") as fh:
            fh.write("agent-ghost\tmax_tool_calls\t5\n")
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc_ghost = main(["--session", sess, "--budget", tsv])
        check("unmatched-lane-scope-exits-2-naming-row", rc_ghost == ERROR and "agent-ghost" in err.getvalue(),
              f"{rc_ghost} {err.getvalue()!r}")

        # A subagent file with no usable lines is reported, never silently dropped.
        with open(os.path.join(sub, "agent-junk.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("{not json\n")
        report_junk = build_report(sess, None)
        check("unusable-subagent-listed", report_junk["unusable_subagents"] == ["agent-junk"],
              str(report_junk.get("unusable_subagents")))
        check("unusable-subagent-budget-could-not-check-exits-2",
              quiet_main(["--session", sess, "--budget"]) == ERROR, "")
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc_text = main(["--session", sess])
        check("unusable-subagent-warned-on-stderr-in-report-mode",
              rc_text == OK and "agent-junk" in err.getvalue(), f"{rc_text} {err.getvalue()!r}")
        os.remove(os.path.join(sub, "agent-junk.jsonl"))

        # Zero usable main turns: the share is undefined, so the gate cannot pass.
        empty = os.path.join(tmp, "empty.jsonl")
        with open(empty, "w", encoding="utf-8") as fh:
            fh.write("{not json\n")
        check("zero-main-turns-budget-could-not-check-exits-2", quiet_main(["--session", empty, "--budget"]) == ERROR, "")

        for bad_row in ("*\tmax_tool_calls\tlots\n", "*\tmax_coffee\t3\n", "*\tmax_tool_calls\n",
                        "agent-wide\tmax_orchestration_share\t0.3\n", "*\tmax_tool_calls\tnan\n",
                        "*\tmax_input_equivalent\tinf\n"):
            with open(tsv, "w", encoding="utf-8") as fh:
                fh.write(bad_row)
            check(f"bad-budget-row-exits-2 {bad_row!r}", quiet_main(["--session", sess, "--budget", tsv]) == ERROR, "")
        check("missing-budget-file-exits-2",
              quiet_main(["--session", sess, "--budget", os.path.join(tmp, "nope.tsv")]) == ERROR, "")

    # -- timestamps (the --since bug): every spelling of one instant parses equal ----
    ref = parse_timestamp("2026-10-14T10:00:00.500000+00:00")
    for spelling in ("2026-10-14T10:00:00.5Z", "2026-10-14T10:00:00.5000001234Z", "2026-10-14T10:00:00.5+0000",
                     "2026-10-14T12:00:00.5+02:00"):
        check(f"timestamp-spelling {spelling}", parse_timestamp(spelling) == ref, str(parse_timestamp(spelling)))
    check("naive-since-is-local-naive-transcript-is-utc",
          parse_timestamp("2026-10-14T10:00:00", local=True) == datetime(2026, 10, 14, 10).astimezone()
          and parse_timestamp("2026-10-14T10:00:00").utcoffset().total_seconds() == 0, "")
    check("two-turns-without-timestamp-sort-without-crash",
          len(extract_turns([{"type": "assistant", "message": {"usage": {"input_tokens": 1}}},
                             {"type": "assistant", "message": {"usage": {"input_tokens": 2}}}])) == 2, "")

    # -- models, effort, in-flight, --top, --rates, context/turn, cheaper-route hint --
    def mturn(req, ts, model, usage, stop=None, content=()):
        msg = {"usage": usage, "model": model, "content": list(content)}
        if stop:
            msg["stop_reason"] = stop
        return json.dumps({"type": "assistant", "timestamp": ts, "requestId": req, "apiBlockIndex": 0,
                           "message": msg}) + "\n"

    with tempfile.TemporaryDirectory() as tmp:
        sess = os.path.join(tmp, "s.jsonl")
        with open(sess, "w", encoding="utf-8") as fh:
            for i in range(6):  # context grows 100k -> 600k; cache reads dominate main
                fh.write(mturn(f"m{i}", f"2026-01-01T00:0{i}:00.5Z", "model-big-20260101",
                               {"input_tokens": 0, "cache_read_input_tokens": 100000 * (i + 1), "output_tokens": 1}))
        sub = os.path.join(tmp, "s", "subagents")
        os.makedirs(sub)
        with open(os.path.join(sub, "agent-a.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(mturn("a1", "2026-01-01T00:01:00Z", "model-big-20260101", {"input_tokens": 1000, "output_tokens": 100}))
            fh.write(mturn("a2", "2026-01-01T00:02:00Z", "model-big-20260101", {"input_tokens": 1000, "output_tokens": 100}))
            fh.write(mturn("a3", "2026-01-01T00:03:00Z", "model-small", {"input_tokens": 1000, "output_tokens": 100},
                           stop="end_turn"))
        with open(os.path.join(sub, "agent-a.meta.json"), "w", encoding="utf-8") as fh:
            json.dump({"effort": "high"}, fh)
        with open(os.path.join(sub, "agent-b.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(mturn("b1", "2026-01-01T00:04:00Z", "model-small", {"input_tokens": 10, "output_tokens": 1}, stop="tool_use"))
        rates_tsv = os.path.join(tmp, "rates.tsv")
        with open(rates_tsv, "w", encoding="utf-8") as fh:
            fh.write("# model\tin\t5m\t1h\tread\tout\nmodel-big\t10\t0\t0\t1\t100\n")
        rates = load_rates(rates_tsv)
        rep = build_report(sess, None, 1, rates)
        lanes = {s["file"]: s for s in rep["all_subagents"]}
        check("lane-majority-model-and-counts", lanes["agent-a"]["model"] == "model-big-20260101"
              and lanes["agent-a"]["models"] == {"model-big-20260101": 2, "model-small": 1}, str(lanes["agent-a"]["models"]))
        check("lane-effort-from-meta-else-none", lanes["agent-a"]["effort"] == "high" and lanes["agent-b"]["effort"] is None, "")
        check("in-flight-lane-flagged-and-still-counted", lanes["agent-b"]["in_flight"] is True
              and lanes["agent-b"]["raw_tokens"] == 11 and lanes["agent-a"]["in_flight"] is False,
              str((lanes["agent-b"]["in_flight"], lanes["agent-b"]["raw_tokens"])))
        check("top-1-lists-one-lane-json-keeps-all", len(rep["top_subagents"]) == 1 and len(rep["all_subagents"]) == 2, "")
        check("top-0-lists-all", len(build_report(sess, None, 0)["top_subagents"]) == 2, "")
        check("subagent-totals-by-model", set(rep["subagents_by_model"]) == {"model-big-20260101", "model-small"}, "")
        # main: cache_read 2.1M * $1/M + 6 out * $100/M ; model-big lane a: 2000 in * $10/M + 200 out * $100/M
        check("main-cost-from-rates", rep["cost_usd"]["main"] == round(2_100_000 * 1 / 1e6 + 6 * 100 / 1e6, 4), str(rep["cost_usd"]))
        check("lane-cost-and-unpriced-model", lanes["agent-a"]["cost_usd"] == round(2000 * 10 / 1e6 + 200 * 100 / 1e6, 4)
              and lanes["agent-a"]["unpriced_models"] == ["model-small"], str(lanes["agent-a"]))
        check("unpriced-model-named-in-total", rep["cost_usd"]["unpriced_models"] == ["model-small"], str(rep["cost_usd"]))
        ctx = rep["main_context"]
        check("context-per-turn-trend-and-handoff", ctx["avg"] == 350000 and ctx["first_third"] == 150000
              and ctx["last_third"] == 550000 and ctx["handoff"] is True, str(ctx))
        text = render_text(rep)
        check("text-has-handoff-flag", "HANDOFF" in text and "start fresh" in text, text)
        check("text-has-cheaper-route-hint-incl-cache-dominated", "Cheaper route:" in text and "cache reads dominate" in text, text)
        check("text-shows-model-usd-and-in-flight", "model=model-big-20260101:2,model-small:1" in text
              and "effort=high" in text and "usd=$" in text, text)
        check("text-total-by-model-blocks", "MAIN by model:" in text and "SUBAGENTS by model:" in text, text)
        check("no-rates-says-UNPRICED", "Cost: UNPRICED" in render_text(build_report(sess, None)), "")
        check("no-rates-json-cost-null", build_report(sess, None)["cost_usd"] is None, "")
        in_flight_text = render_text(build_report(sess, None, 0))
        check("in-flight-marker-in-text", "in-flight" in in_flight_text, in_flight_text)
        for bad in ("m\t1\t2\n", "m\t1\t2\t3\t4\tx\n", "m\t1\t2\t3\t4\t-5\n"):
            with open(rates_tsv, "w", encoding="utf-8") as fh:
                fh.write(bad)
            check(f"bad-rates-exits-2 {bad!r}", quiet_main(["--session", sess, "--rates", rates_tsv]) == ERROR, "")
        check("missing-rates-exits-2", quiet_main(["--session", sess, "--rates", os.path.join(tmp, "nope")]) == ERROR, "")
        # empty window explains itself on stderr instead of a silent zero report
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc_empty = main(["--session", sess, "--since", "2099-01-01T00:00:00Z"])
        check("empty-window-warns-with-span", rc_empty == OK and "matched no turns" in err.getvalue()
              and "2026-01-01" in err.getvalue(), err.getvalue())
        check("window-boundary-with-fraction-keeps-turn", build_report(
            sess, parse_timestamp("2026-01-01T00:05:00.5Z"))["main_turns"] == 1, "")

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        print(f"token_report.py selftest: {len(failures)} failure(s)")
        return ERROR
    print("token_report.py selftest: ok")
    return OK


if __name__ == "__main__":
    sys.exit(main())
