#!/usr/bin/env python3
"""Per-arm cost capture for rival_eval.py, without editing it (its sha256 is frozen by test_evil_twin_bench_r2.py).

usage: rival_eval_cost.py run ...   (same arguments as rival_eval.py)

`install()` wraps rival_eval's `generate`, `save` and `run_skill` and shims its `urllib`/`subprocess` so that the real usage
reported by the PCSS response (`usage.prompt_tokens`, `completion_tokens`, `cost`) or the `claude -p` result line
(`usage`, `total_cost_usd`) is written next to each generated output as `<id>-<hash>.usage.json` (so a resumed run keeps the
numbers of cached outputs), and `run_skill` adds `cost_per_arm` to results.json. Nothing is estimated: an arm whose items
reported no usage stays unmeasured. `bench_verdict.py --cost results.json` reads the result. Side effects: results.json is
rewritten after run_skill; no network or process is added beyond what rival_eval already does.
"""
import functools
import io
import json
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rival_eval as r  # noqa: E402

_tl = threading.local()  # usage of the latest call on this thread (generation runs in a thread pool)
_TOKENS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def chat_usage(body):
    """PCSS response body (dict) -> usage dict, or {} when the API reports no token counts. spend_usd is None (unmeasured) without usage.cost."""
    u = body.get("usage") or {}
    if "prompt_tokens" in u and "completion_tokens" in u:
        return dict(prompt_tokens=u["prompt_tokens"], completion_tokens=u["completion_tokens"], spend_usd=u.get("cost"))
    return {}


def claude_usage(stdout):
    """`claude -p` stream-json stdout -> usage dict from its result line, or {} when absent."""
    for line in stdout.splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            continue
        u = j.get("usage") or {}
        if j.get("type") == "result" and "total_cost_usd" in j and "input_tokens" in u and "output_tokens" in u:
            return dict(prompt_tokens=sum(u.get(k) or 0 for k in _TOKENS), completion_tokens=u["output_tokens"], spend_usd=float(j["total_cost_usd"] or 0))
    return {}


def arm_cost(arm_usage, n_items):
    """Sum per-item usage dicts (items without a reported usage are left out, never estimated) -> per-arm cost record."""
    paid = bool(arm_usage) and all(u.get("spend_usd") is not None for u in arm_usage)  # one missing price: dollars unmeasured
    return dict(n_measured=len(arm_usage), n_items=n_items,
                **{k: round(sum(u[k] for u in arm_usage), 6) for k in ("prompt_tokens", "completion_tokens")},
                spend_usd=round(sum(u["spend_usd"] for u in arm_usage), 6) if paid else None)


class _Shim:
    """A module look-alike: `over` attributes replace the real ones, everything else is the real module's."""
    def __init__(self, mod, **over):
        self._mod, self._over = mod, over

    def __getattr__(self, k):
        return self._over[k] if k in self._over else getattr(self._mod, k)


def _urlopen(*a, **k):
    _tl.usage = {}  # a failed or retried call leaves nothing behind
    body = urllib.request.urlopen(*a, **k).read()
    try:
        _tl.usage = chat_usage(json.loads(body))
    except (ValueError, AttributeError):
        pass
    return io.BytesIO(body)


def _run(*a, **k):
    _tl.usage = {}
    p = subprocess.run(*a, **k)
    if isinstance(p.stdout, str):
        _tl.usage = claude_usage(p.stdout)
    return p


def install():
    """Wrap rival_eval in place (idempotent). Call before rival_eval.main()."""
    if getattr(r, "_cost_installed", False):
        return
    r._cost_installed = True
    r.urllib = _Shim(urllib, request=_Shim(urllib.request, urlopen=_urlopen))
    r.subprocess = _Shim(subprocess, run=_run)
    gen, save, run_skill = r.generate, r.save, r.run_skill

    @functools.wraps(gen)
    def generate(*a, **k):
        _tl.usage = {}
        txt = gen(*a, **k)
        _tl.pending = dict(_tl.usage)  # the output about to be saved on this thread owns this usage
        return txt

    @functools.wraps(save)
    def save_(p, text):
        save(p, text)
        u, _tl.pending = getattr(_tl, "pending", None), None
        if u:
            p.with_suffix(".usage.json").write_text(json.dumps(u))

    @functools.wraps(run_skill)
    def run_skill_(skill, split, backend, out, jobs, cap):
        res = run_skill(skill, split, backend, out, jobs, cap)
        scs = r.load_scenarios(skill, split)
        d = max((out / skill).glob(f"{split}-*/results.json"), key=lambda f: f.stat().st_mtime).parent  # the dir run_skill just wrote
        uses = {a: [json.loads(f.read_text()) for sc in scs
                    if (f := d / "outputs" / a / f"{sc['id']}-{r.sha(sc['prompt'])[:8]}.usage.json").exists()] for a in r.ARMS}
        res["cost_per_arm"] = {a: arm_cost(uses[a], len(scs)) for a in r.ARMS}
        (d / "results.json").write_text(json.dumps(res, indent=1) + "\n")
        return res

    r.generate, r.save, r.run_skill = generate, save_, run_skill_


if __name__ == "__main__":
    install()
    sys.exit(r.main())
