"""Self-test: the arm stops on the first infrastructure fault and probes connectivity first. sh_claude is faked; no network, no paid call."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agentic_arm as A


def fixtures(n=3):
    d = Path(tempfile.mkdtemp())
    for i in range(n):
        (d / f"fx{i}" / ".git").mkdir(parents=True)
    return d


def fake(calls, **kw):
    def f(*a, **k):
        calls.append(1)
        return dict(text="", cost=0.0, util=None, err="", subtype="", returncode=1, stderr="", denials=[], init_skills=["perun:deep-code-review"], skill_loaded=False, raw="") | kw
    return f


def run_with(calls, probe=None, **kw):
    A.sh_claude = fake(calls, **kw)
    out = Path(tempfile.mkdtemp()) / "out"
    errs = A.run(out.parent, out, fixtures(), **({"probe": probe} if probe else {}))[2]
    return out, errs


def test_tunnel_error_stops_after_first_fixture():
    calls = []
    out, errs = run_with(calls, err="claude error: ERR_PROXY_TUNNEL")
    stops = [e["stop"] for e in errs if "stop" in e]
    assert len(calls) == 1 and stops and "infrastructure fault" in stops[0] and "fx0" in stops[0]
    assert "infrastructure fault" in json.load(open(out / "errors.json"))["errors"][-1]["stop"]


def test_zero_cost_no_skill_is_infra_fault():
    calls = []
    errs = run_with(calls, text="x")[1]
    assert len(calls) == 1 and "infrastructure fault" in errs[-1]["stop"]


def test_model_error_keeps_going():
    calls = []
    errs = run_with(calls, err="empty report", cost=0.4)[1]
    assert len(calls) == 3 and not any("infrastructure" in e.get("stop", "") for e in errs)


def test_probe_failure_makes_zero_calls():
    calls = []

    def bad():
        raise OSError("Tunnel connection failed: 403 Forbidden")
    out, errs = run_with(calls, probe=bad)
    assert not calls and "infrastructure fault" in errs[-1]["stop"] and (out / "errors.json").exists()


def test_probe_ok_proceeds():
    calls = []
    run_with(calls, probe=lambda: None, err="empty report", cost=0.4)
    assert len(calls) == 3


def test_probe_api_treats_http_status_as_reachable():
    import urllib.error
    real = A.urllib.request.urlopen
    try:
        A.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(urllib.error.HTTPError("u", 404, "nf", {}, None))
        A.probe_api()
        A.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("Tunnel connection failed"))
        try:
            A.probe_api()
            raise SystemExit("no raise")
        except urllib.error.URLError:
            pass
    finally:
        A.urllib.request.urlopen = real


if __name__ == "__main__":
    n = 0
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f(); n += 1
    print("Tests: %d/%d" % (n, n))
