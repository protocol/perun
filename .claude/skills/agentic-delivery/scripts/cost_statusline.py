#!/usr/bin/env python3
"""cost_statusline.py — statusLine command: one line of session cost, context fill, prompt-cache health and the active 5-hour window.

Claude Code pipes a JSON session object to the statusLine command on stdin and shows what it prints. This prints
`est $0.12 | ctx 43% | cache 91%` from `cost.total_cost_usd` (a client-side list-price estimate, not a bill),
`context_window.used_percentage` and `prompt_cache.hit_ratio`, plus `miss <cause>` when the host names a cache-miss
cause. A field the host did not send is left out; with none of them it prints nothing, which blanks the status line
(the host's documented behaviour for empty output), and it never fails.

When the sibling `agentic-ceo/scripts/token_report.py` is installed and the host sends `transcript_path`, it also
appends the active 5-hour window: `win 2h10m left | 62% | +14k/min` (time left, the host's
`rate_limits.five_hour.used_percentage`, and the window's weighted-token burn per minute from `token_report.burn_blocks`).
From the last TAIL bytes of the transcript it parses as JSON every whole line that mentions "usage" (a line is parsed
whole to find its fields) and keeps only requestId, apiBlockIndex, timestamp, isSidechain, type, message.model and
message.usage of main-thread turns; no message content is kept, printed or sent anywhere.
Time left comes from the host's `rate_limits.five_hour.resets_at` when it is sent and sane (finite, at most one window
ahead), else from the modelled window. A modelled window or burn rate read from a clipped tail is marked `~` unless the
tail holds a gap of a whole window between two turns, which anchors the block chain exactly. A missing
`prompt_cache.hit_ratio` is computed from the same tail and shown as `tail cache N%`, distinct from the host's
session-wide `cache N%`. Without token_report, without a readable transcript, or on any error, the output is the plain
fields above (the tail cache share survives a window failure).

Install wires it into `.claude/settings.local.json` only when no user, project or local settings file already sets
`statusLine`; uninstall removes it again. Run `cost_statusline.py --selftest` to check it.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TAIL = 1 << 20  # bytes of transcript read; ponytail: bigger = truer window start but slower (the token_report import already costs ~60ms)
_num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)  # noqa: E731


def _tail_turns(path, tr):
    """Main-thread turns from the last TAIL bytes of the transcript, plus whether the tail was clipped. Reads only lines that mention "usage" and keeps their request/timestamp/sidechain/type keys plus message model and usage (what the window model needs)."""
    with open(path, "rb") as fh:
        size = os.fstat(fh.fileno()).st_size
        fh.seek(max(0, size - TAIL))
        data = fh.read()
    lines = data.split(b"\n")[1 if size > TAIL else 0:]  # the first line of a clipped tail is cut mid-line
    keep = ("requestId", "apiBlockIndex", "timestamp", "isSidechain", "type")
    entries = []
    for ln in lines:
        if b'"usage"' not in ln:
            continue
        try:
            e = json.loads(ln)
            m = e["message"]
            entries.append({**{k: e.get(k) for k in keep}, "message": {"model": m.get("model"), "usage": m.get("usage")}})
        except (ValueError, KeyError, AttributeError, TypeError):
            continue
    return tr.extract_turns(entries, main=True), size > TAIL


def _window(data, now=None):
    """`(window parts, tail hit ratio)` from the transcript tail; each is empty/None when token_report or the transcript is unavailable or it fails."""
    try:
        # bytecode goes to a user-owned cache (not shared /tmp: a planted .pyc would run), not __pycache__ in the skills tree:
        # without any cache the 2800-line module recompiled on every refresh. Limit: PYTHONDONTWRITEBYTECODE=1 (or -B) turns
        # the cache off, so that refresh recompiles each time
        keep, sys.pycache_prefix = sys.pycache_prefix, sys.pycache_prefix or os.path.expanduser("~/.cache/perun-pyc")
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agentic-ceo" / "scripts"))
        try:
            import token_report as tr  # noqa: E402
        finally:
            sys.pycache_prefix = keep
        turns, clipped = _tail_turns(data["transcript_path"], tr)
        now = now or datetime.now(timezone.utc)
        live = [t for t in turns if not t.get("iter") and t["timestamp"] and t.get("model") != "<synthetic>"]
        reads = sum(t["cache_read"] for t in live)
        denom = reads + sum(t["cache_write_5m"] + t["cache_write_1h"] + t["input_tokens"] for t in live)
        ratio = reads / denom if denom else None
    except Exception:  # fail-silent: any error leaves the plain fields
        return [], None
    try:  # a window failure must not drop the tail cache share
        act = tr.burn_blocks(turns, [], now=now)["active"] or {}
        win = (data.get("rate_limits") or {}).get("five_hour") or {}
        reset = win.get("resets_at")
        exact = _num(reset) and 0 < reset - now.timestamp() <= tr.BLOCK_S  # a sane host reset time: finite, within one window
        # a clipped tail anchors the modelled block chain only after a gap of a whole window between two turns in it
        gap = timedelta(seconds=tr.BLOCK_S)
        sure = not clipped or any(b["timestamp"] - a["timestamp"] >= gap for a, b in zip(live, live[1:]))
        mark = "" if sure else "~"
        rem = (reset - now.timestamp()) / 60 if exact else act.get("remaining_min")
        parts = []
        if _num(rem) and rem > 0:
            tm = "" if exact else mark
            parts.append(f"win {tm}{int(rem) // 60}h{int(rem) % 60:02d}m left" if rem >= 60 else f"win {tm}{int(rem)}m left")
            pct, rate = win.get("used_percentage"), act.get("burn_per_min")
            if _num(pct):
                parts.append(f"{pct:.0f}%")
            if _num(rate):
                parts.append(f"{mark}+{rate / 1000:.0f}k/min" if rate >= 1000 else f"{mark}+{rate:.0f}/min")
        return parts, ratio
    except Exception:
        return [], ratio


def render(data, now=None):
    """The status line text for one session object, or "" when it carries none of its fields. `now` is for tests."""
    if not isinstance(data, dict):
        return ""
    get = lambda obj, key: obj.get(key) if isinstance(obj, dict) else None  # noqa: E731
    cost = get(data.get("cost"), "total_cost_usd")
    ctx = get(data.get("context_window"), "used_percentage")
    cache = data.get("prompt_cache")
    host_ratio = ratio = get(cache, "hit_ratio")
    cause = get(get(cache, "last_miss_cause"), "causes")
    num = _num
    win, tail_ratio = _window(data, now) if isinstance(data.get("transcript_path"), str) else ([], None)
    ratio = ratio if num(ratio) else tail_ratio
    parts = [f"est ${cost:.2f}" if num(cost) else "", f"ctx {ctx:.0f}%" if num(ctx) else "",
             f"{'cache' if num(host_ratio) else 'tail cache'} {ratio * 100:.0f}%" if num(ratio) else "",
             f"miss {cause[0]}" if isinstance(cause, list) and cause and isinstance(cause[0], str) else ""] + win
    return " | ".join(p for p in parts if p)


def _selftest():
    full = {"cost": {"total_cost_usd": 0.1234}, "context_window": {"used_percentage": 42.6},
            "prompt_cache": {"hit_ratio": 0.912, "last_miss_cause": {"causes": ["ttl_expired_5m"]}}}
    cases = [(full, "est $0.12 | ctx 43% | cache 91% | miss ttl_expired_5m"),
             ({"cost": {"total_cost_usd": 0}}, "est $0.00"),
             ({"prompt_cache": {"hit_ratio": None, "last_miss_cause": None}}, ""),
             ({"cost": {"total_cost_usd": "x"}, "context_window": []}, ""),
             ([], ""), ({}, "")]
    bad = [(c, w, render(c)) for c, w in cases if render(c) != w]
    print("selftest:", "ok" if not bad else bad)
    return 1 if bad else 0


def main():
    try:
        out = render(json.load(sys.stdin))
    except Exception:  # noqa: BLE001 - a status line never prints an error
        out = ""
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(_selftest() if "--selftest" in sys.argv else main())
