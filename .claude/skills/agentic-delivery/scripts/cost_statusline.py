#!/usr/bin/env python3
"""cost_statusline.py — statusLine command: one line of session cost, context fill and prompt-cache health.

Claude Code pipes a JSON session object to the statusLine command on stdin and shows what it prints. This prints
`est $0.12 | ctx 43% | cache 91%` from `cost.total_cost_usd` (a client-side list-price estimate, not a bill),
`context_window.used_percentage` and `prompt_cache.hit_ratio`, plus `miss <cause>` when the host names a cache-miss
cause. A field the host did not send is left out; with none of them it prints nothing, which blanks the status line
(the host's documented behaviour for empty output), and it never fails.

Install wires it into `.claude/settings.local.json` only when no user, project or local settings file already sets
`statusLine`; uninstall removes it again. Run `cost_statusline.py --selftest` to check it.
"""
import json
import sys


def render(data):
    """The status line text for one session object, or "" when it carries none of the three fields."""
    if not isinstance(data, dict):
        return ""
    get = lambda obj, key: obj.get(key) if isinstance(obj, dict) else None  # noqa: E731
    cost = get(data.get("cost"), "total_cost_usd")
    ctx = get(data.get("context_window"), "used_percentage")
    cache = data.get("prompt_cache")
    ratio = get(cache, "hit_ratio")
    cause = get(get(cache, "last_miss_cause"), "causes")
    num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)  # noqa: E731
    parts = [f"est ${cost:.2f}" if num(cost) else "", f"ctx {ctx:.0f}%" if num(ctx) else "",
             f"cache {ratio * 100:.0f}%" if num(ratio) else "",
             f"miss {cause[0]}" if isinstance(cause, list) and cause and isinstance(cause[0], str) else ""]
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
    except (ValueError, OSError):
        out = ""
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(_selftest() if "--selftest" in sys.argv else main())
