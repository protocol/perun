#!/usr/bin/env python3
"""Validate an idea-critic verdict JSON file.

Exit 0 = valid, 1 = contract violation, 2 = usage or unreadable input.
Stdlib only. Reports field names, never file contents that might be private.
"""
from __future__ import annotations

import datetime
import json
import sys
import unicodedata
from pathlib import Path
from typing import NoReturn

REQUIRED = (
    "verdict",
    "independence",
    "origin",
    "claim",
    "steelman",
    "hats_run",
    "assumptions",
    "better_ways",
    "kill_criteria",
    "strongest_attack_survived",
    "questions_parent_must_resolve",
    "user_question",
    "dissent_ledger",
    "remaining_risk",
)
COUNCIL = (  # veche.py decision record (has "tally"); see references/council.md
    "verdict", "independence", "origin", "claim", "steelman", "tally",
    "confidence", "dissent", "what_would_change_it", "cost",
)
VERDICTS = {"HOLD", "REVISE", "PASS_TO_USER"}
INDEPENDENCE = {"inline", "independent"}
ORIGINS = {"owner-request", "agent-originated"}
FINDING_CLASSES = {"real", "misread", "accepted-cost", "noise"}
# Typographic variants fold to ASCII; zero-width characters vanish (norm in check_findings).
_FOLD = {
    **dict.fromkeys([*range(0x2018, 0x201C), 0x2032], "'"),  # curly single quotes, prime
    **dict.fromkeys(range(0x201C, 0x2020), '"'),  # curly double quotes
    **dict.fromkeys([*range(0x2010, 0x2016), 0x2212], "-"),  # dashes, minus
    **dict.fromkeys([0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD], None),  # zero-width, word joiner, soft hyphen
}
MIN_QUOTE = 12  # chars after normalizing; shorter quotes match almost anything
# Phrases that read as a performative, non-attacking "attack" — a
# strongest_attack_survived that reduces to one of these defeats the point
# of the field (see idea-critic/SKILL.md, verdict schema).
GENERIC_PASS_PHRASES = {
    "none",
    "n/a",
    "na",
    "no issues found",
    "no issues",
    "looks good",
    "nothing",
    "no objections",
    "no attack",
    "not applicable",
}


def die(code: int, msg: str) -> NoReturn:
    print(f"validate_verdict: {msg}", file=sys.stderr)
    raise SystemExit(code)


def check_findings(data: dict, artifact: Path | None, council: bool) -> None:
    """Optional findings: [{text, class, quote}]. Shape, class and quote length
    are checked whenever present; an independent REVISE/HOLD then needs at
    least one `real` finding. With --artifact each quote must also occur in the
    artifact (NFKC, case-folded, quotes and dashes to ASCII, zero-width
    characters dropped, whitespace collapsed) and the artifact makes findings
    mandatory for that REVISE/HOLD. `"findings": null` is an error."""
    if "findings" not in data and artifact is None:
        return
    found = data.get("findings", [])
    if not isinstance(found, list):
        die(1, "findings must be a list")

    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKC", s).casefold().translate(_FOLD)
        return " ".join(s.split())

    for i, f in enumerate(found):
        if not isinstance(f, dict):
            die(1, f"findings[{i}] must be an object")
        if not isinstance(f.get("class"), str) or f["class"] not in FINDING_CLASSES:
            die(1, f"findings[{i}].class must be one of: {', '.join(sorted(FINDING_CLASSES))}")
        for k in ("text", "quote"):
            if not isinstance(f.get(k), str) or not f[k].strip():
                die(1, f"findings[{i}].{k} must be a non-empty string")
        if len(norm(f["quote"])) < MIN_QUOTE:
            die(1, f"findings[{i}].quote must be at least {MIN_QUOTE} characters")
    if artifact is not None:
        try:
            text = norm(artifact.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            die(2, "unreadable artifact")
        for i, f in enumerate(found):
            if norm(f["quote"]) not in text:
                die(1, f"findings[{i}].quote is not in the artifact")
    if (
        not council
        and data["verdict"] in ("REVISE", "HOLD")
        and data["independence"] != "inline"
        and not any(f["class"] == "real" for f in found)
    ):
        die(1, f"an independent {data['verdict']} requires at least one real finding")


def main(argv: list[str]) -> int:
    usage = "usage: validate_verdict.py --file <verdict.json> [--artifact <file>]"
    opts: dict[str, str] = {}
    args = iter(argv[1:])
    for flag in args:
        name = {"-f": "--file"}.get(flag, flag)
        if name not in ("--file", "--artifact") or name in opts:
            die(2, usage)
        value = next(args, None)
        if value is None or value.startswith("-"):
            die(2, f"missing value for {flag}")
        opts[name] = value
    if "--file" not in opts:
        die(2, usage)
    path = Path(opts["--file"])
    artifact = Path(opts["--artifact"]) if "--artifact" in opts else None
    if not path.is_file():
        die(2, f"not a file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        die(2, "unreadable or malformed JSON")
    if not isinstance(data, dict):
        die(1, "verdict must be a JSON object")

    council = "tally" in data
    missing = [k for k in (COUNCIL if council else REQUIRED) if k not in data]
    if missing:
        die(1, f"missing key(s): {', '.join(missing)}")

    verdict = data["verdict"]
    origin = data["origin"]
    independence = data["independence"]
    user_q = data.get("user_question")
    steelman = data["steelman"]
    strongest_attack = data.get("strongest_attack_survived")

    for k in ("decision", "leading_metric"):  # optional closers (SKILL.md Decision method step 6): never empty when present
        if k in data and (not isinstance(data[k], str) or not data[k].strip()):
            die(1, f"{k} must be a non-empty string when present")
    if council:
        if verdict in ("COULD_NOT_DECIDE", "NOT_CONVENED"):
            if not str(data.get("reason", "")).strip():
                die(1, f"{verdict} requires a non-empty reason")
        elif verdict not in VERDICTS:
            die(1, "verdict must be HOLD | REVISE | PASS_TO_USER | COULD_NOT_DECIDE | NOT_CONVENED")
        if "decision" in data and verdict in VERDICTS:  # a Veche option decision carries its closers
            if not isinstance(data.get("kill_criteria"), list) or not data["kill_criteria"]:
                die(1, "a Veche decision requires a non-empty kill_criteria list")
            try:
                datetime.date.fromisoformat(str(data.get("review_date")))
            except ValueError:
                die(1, "a Veche decision requires an ISO review_date")
            if "leading_metric" not in data:
                die(1, "a Veche decision requires leading_metric")
        conf = data["confidence"]
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
            die(1, "confidence must be a number in [0, 1]")
        if not data["what_would_change_it"] or not isinstance(data["what_would_change_it"], list):
            die(1, "what_would_change_it must be a non-empty list")
    elif verdict not in VERDICTS:
        die(1, "verdict must be HOLD | REVISE | PASS_TO_USER")
    if origin not in ORIGINS:
        die(1, "origin must be owner-request | agent-originated")
    if independence not in INDEPENDENCE:
        die(1, "independence must be inline | independent")
    if origin == "owner-request" and verdict == "HOLD":
        die(1, "owner-request + HOLD is illegal")
    if council:
        user_q, strongest_attack = "NONE", "n/a-council"  # council has no user_question
    if isinstance(user_q, list):
        die(1, "user_question must be one line or NONE, never a list")
    if not isinstance(user_q, str) or not user_q.strip():
        die(1, "user_question must be a non-empty string or NONE")
    if not isinstance(steelman, str) or not steelman.strip():
        die(1, "steelman must be a non-empty string")
    # Only PASS_TO_USER is checked for content: HOLD/REVISE never reach the
    # owner, so a thin strongest_attack_survived there is not yet the defect
    # this field exists to catch (it becomes one the moment the verdict
    # would surface unattacked to the owner).
    if verdict == "PASS_TO_USER":
        if not isinstance(strongest_attack, str) or not strongest_attack.strip():
            die(1, "PASS_TO_USER requires a non-empty strongest_attack_survived")
        if strongest_attack.strip().lower() in GENERIC_PASS_PHRASES:
            die(
                1,
                "strongest_attack_survived reads as generic/performative, not a real attack",
            )
    check_findings(data, artifact, council)
    print("validate_verdict: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
