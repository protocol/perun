#!/usr/bin/env python3
"""Hypothesis property tests for the parsers behind Perun's safety gates: the command splitter shared by heavy_gate.py, the deny/allow
decision of destructive_guard.py, the secret scanner's matching, and the lease-record parser in perun_policy.py. Skips cleanly (exit 0, one
line) when `hypothesis` is not installed, so CI never needs it; install it in a venv to run: `python3 scripts/test_property_parsers.py`
(or pytest). Deterministic (derandomize, no example database), offline."""
import hashlib, math, os, pathlib, re, sys, tempfile

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
AD = HERE.parent / ".claude/skills/agentic-delivery/scripts"
sys.path[:0] = [str(HERE), str(AD)]

try:
    from hypothesis import HealthCheck, given, settings, strategies as st
except ImportError:
    if __name__ == "__main__":
        print("skip: hypothesis not installed")
        sys.exit(0)
    import pytest
    pytest.skip("hypothesis not installed", allow_module_level=True)

import destructive_guard as dg  # noqa: E402
import heavy_gate as hg  # noqa: E402
import perun_policy as pp  # noqa: E402
import secret_scan as ss  # noqa: E402

S = settings(max_examples=150, deadline=None, derandomize=True, database=None, suppress_health_check=list(HealthCheck))
WORD = st.text("abcdefgh-_./=0123456789", min_size=1, max_size=8)
HEAVY = ["pytest", "npm test", "cargo test", "go test ./...", "python -m pytest tests/", "bash -c 'pytest'", "uv run pytest -q", "next build"]
BAD = ["rm -rf /", "rm -rf ~", "git push --force origin main", "git reset --hard", "dd if=/dev/zero of=/dev/sda", "chmod -R 777 /", "mkfs.ext4 /dev/sda1"]
NOISE = st.text(max_size=60).filter(lambda s: "\n" not in s and "gitleaks" not in s.lower())
KIND = st.from_regex(r"[A-Za-z][A-Za-z-]{0,15}", fullmatch=True)
PRE = ["", "cd x && ", "ls; ", "echo hi | ", "true || "]
POST = ["", " && ls", "; echo done"]


@S
@given(st.text(max_size=200))
def test_splitter_total(text):
    """tokens/segments return lists or raise ValueError (unbalanced quote); nothing else."""
    for fn in (hg.tokens, hg.segments):
        try:
            out = fn(text)
        except ValueError:
            continue
        assert isinstance(out, list)


@S
@given(st.lists(st.text("abc ;|&\t", max_size=12), max_size=6))
def test_tokens_keep_every_non_space_char(parts):
    text = "\n".join(parts)
    assert "".join(re.sub(r"\s", "", t) for t in hg.tokens(text)) == re.sub(r"\s", "", text)


@S
@given(st.lists(WORD, min_size=1, max_size=4), st.lists(WORD, min_size=1, max_size=4))
def test_segments_split_on_operators(a, b):
    for op in (";", "&&", "|"):
        assert hg.segments(" ".join(a) + f" {op} " + " ".join(b)) == [a, b]


@S
@given(st.sampled_from(HEAVY), st.sampled_from(PRE), st.sampled_from(POST))
def test_heavy_stays_heavy_inside_a_chain(cmd, pre, post):
    assert hg.is_heavy(cmd, hg.DEFAULT_PATTERNS) and hg.is_heavy(pre + cmd + post, hg.DEFAULT_PATTERNS)


@S
@given(st.sampled_from([c for c in HEAVY if "'" not in c]), st.sampled_from(["echo", "printf %s", "grep -n"]))
def test_quoted_argument_is_never_heavy(cmd, head):
    assert not hg.is_heavy(f"{head} '{cmd}'", hg.DEFAULT_PATTERNS)


@S
@given(st.text(max_size=300))
def test_is_heavy_never_raises(text):
    assert hg.is_heavy(text, hg.DEFAULT_PATTERNS) in (True, False)


@S
@given(st.text(max_size=300))
def test_guard_total_and_deterministic(text):
    r = dg.check(text)
    assert isinstance(r, str) and dg.check(text) == r


@S
@given(st.sampled_from(BAD), st.sampled_from(PRE), st.sampled_from(POST))
def test_guard_denial_survives_chaining(bad, pre, post):
    assert dg.check(bad), bad
    assert dg.check(pre + bad + post), (pre, bad, post)


@S
@given(st.text(max_size=400))
def test_scan_total(text):
    ids = ss.gitleaks_rule(text, "f.txt", True)
    assert isinstance(ids, list) and ids == ss.gitleaks_rule(text, "f.txt", True)


@S
@given(st.lists(NOISE, max_size=3), st.lists(NOISE, max_size=3))
def test_known_secret_found_among_noise(before, after):
    al = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    secret = "ghp_" + "".join(al[b % 62] for b in hashlib.sha256(b"prop").digest() * 2)[:36]
    line = f"t = {secret}"
    assert "github-pat" in ss.gitleaks_rule("\n".join(before + [line] + after), "f.txt")
    assert "github-pat" not in ss.gitleaks_rule("\n".join(before + [line + "  # gitleaks:allow"] + after), "f.txt")


@S
@given(st.text(max_size=300))
def test_bench_ids_cover_gate_ids(text):
    """Every plain gitleaks rule the gate (precise) reports is also reported by the bench path (not precise)."""
    extra = {e[0] for e in ss.EXTRA}
    gate = {i for i in ss.gitleaks_rule(text, "f.txt", True) if i not in extra}
    assert gate <= set(ss.gitleaks_rule(text, "f.txt", False))


@S
@given(st.text(max_size=80))
def test_entropy_bounds_and_order_invariance(s):
    e = ss.entropy(s)
    assert -1e-9 <= e <= (math.log2(len(set(s))) if s else 0) + 1e-9
    assert abs(e - ss.entropy("".join(sorted(s)))) < 1e-9


@S
@given(st.integers(0, 7_000), st.one_of(st.none(), KIND))
def test_lease_record_round_trip(age, kind):
    now = 10_000_000.0
    pid = os.getpid()
    with tempfile.TemporaryDirectory() as t:
        d = pathlib.Path(t)
        start = int(now) - age
        (d / "x").write_text(f"{pid} {start}" + (f" {kind}" if kind else ""))
        assert pp._leases(d, now) == ([(pid, start, kind)] if age < pp.LEASE_TTL else [])


@S
@given(st.text(max_size=60))
def test_lease_parser_never_raises_on_garbage(body):
    with tempfile.TemporaryDirectory() as t:
        d = pathlib.Path(t)
        (d / "x").write_text(body)
        assert isinstance(pp._leases(d, 1e9), list)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
