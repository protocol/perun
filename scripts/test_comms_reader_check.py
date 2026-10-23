#!/usr/bin/env python3
"""Offline tests for communication-structure reader_check.py and evals/reader-checks.json.

No model call. Fails if a key stops matching a source-faithful message, matches the raw
source notes (echo-only), accepts keyword stuffing or the wrong polarity, or the CLI
crashes on bad input.
"""
import json, re, subprocess, sys, tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
S = ROOT / ".claude/skills/communication-structure"
sys.path.insert(0, str(S / "scripts"))
from reader_check import score

CHECKS = json.loads((S / "evals/reader-checks.json").read_text())
BY = {c["id"]: c for c in CHECKS}
PROMPTS = {s["id"]: s["prompt"] for s in json.loads((ROOT / "docs/bench/comms-outcome-1019/scenarios_held.json").read_text())}
FULL = lambda c: (len(c["questions"]),) * 2 + ([],)


def test_five_scenarios_with_two_or_three_questions_each():
    assert len(CHECKS) == 5
    for c in CHECKS:
        assert c["id"] in PROMPTS and 2 <= len(c["questions"]) <= 3, c["id"]


def test_good_message_scores_full_marks():
    for c in CHECKS:
        assert score(c["good"], c["questions"]) == FULL(c), c["id"]


def test_source_notes_alone_score_zero():  # no echo-only keys
    for c in CHECKS:
        assert score(PROMPTS[c["id"]], c["questions"])[0] == 0, c["id"]


def test_every_number_and_name_in_a_key_is_in_the_source():
    for c in CHECKS:
        for q in c["questions"]:
            for k in q["all"]:
                k = re.sub(r"\{[^}]*\}|\[[^\]]*\]|\\[bdsw]|\(\?i\)", " ", k).replace("\\", "")
                for tok in re.findall(r"\$?\d[\d.,]*[%kKM]?|\b[A-Z][a-z]+\b|\bUT\b", k):
                    assert tok.rstrip(".,") in PROMPTS[c["id"]], (c["id"], tok)


def test_degraded_messages_lose_points():
    for c in CHECKS:
        n, lines = len(c["questions"]), c["good"].splitlines()
        assert score(lines[0], c["questions"])[0] < n, c["id"]  # lead only: no figure, no trade-offs
        assert score("\n".join(l for l in lines if not l.startswith("Key figure:")), c["questions"])[0] < n, c["id"]
        assert score("Thanks for waiting.\n" + "\n".join(lines[1:]), c["questions"])[0] < n, c["id"]  # answer not on line 1


def test_keyword_stuffing_fails_and_paraphrase_passes():
    q = BY["held02"]["questions"]
    stuffed = "Tom retrofit both lines Line 1 January Thursday 14th " + "filler " * 60
    assert score(stuffed, q)[0] == 0
    ok = "Tom: decide by Thu 14th. Options: retrofit both lines, Line 1 only, or wait till January.\nKey figure: 92.4% pick accuracy.\n$1.35M against $1.8M; the slot slips to November and we lose the rebate."
    assert score(ok, q)[0] == 3


def test_wrong_polarity_fails():
    for i, a, b in (("held02", "we lose the rebate", "we keep the rebate"), ("held08", "we lose the vendor discount", "we keep the vendor discount")):
        c = BY[i]
        assert a in c["good"] and score(c["good"].replace(a, b), c["questions"])[0] == len(c["questions"]) - 1, i


def test_ut_does_not_match_inside_words():
    q = BY["held05"]["questions"][:1]
    assert score("Dana, 5th Street, the Domain, or but output Friday", q)[0] == 0
    assert score("Dana, 5th Street, the Domain, or near UT, by Friday", q)[0] == 1


def test_empty_edges():
    assert score("", CHECKS[0]["questions"])[0] == 0
    assert score("anything", []) == (0, 0, [])


def cli(*args):
    r = subprocess.run([sys.executable, "-I", str(S / "scripts/reader_check.py"), *args], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def test_cli_exit_codes():
    ck = str(S / "evals/reader-checks.json")
    with tempfile.TemporaryDirectory() as d:
        good, bad, rx = Path(d, "g.md"), Path(d, "b.md"), Path(d, "rx.json")
        good.write_text(BY["held02"]["good"])
        bad.write_text("Thanks.")
        rx.write_text('[{"id": "x", "questions": [{"q": "q", "scope": "all", "all": ["("]}]}]')
        assert cli("--checks", ck, "--id", "held02", "--file", str(good))[:2] == (0, "3/3\n")
        assert cli("--checks", ck, "--id", "held02", "--file", str(bad))[0] == 1
        for args in (("--checks", ck, "--id", "nope", "--file", str(good)),
                     ("--checks", ck, "--id", "held02", "--file", str(Path(d, "missing.md"))),
                     ("--checks", str(rx), "--id", "x", "--file", str(good)),
                     ("--checks", str(Path(d, "gone.json")), "--id", "x", "--file", str(good))):
            code, _, err = cli(*args)
            assert code == 2 and err.startswith("reader_check:"), args


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("comms reader_check: all tests passed")
