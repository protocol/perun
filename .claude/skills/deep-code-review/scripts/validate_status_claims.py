#!/usr/bin/env python3
"""Flag a completion status that carries a caveat — "a ✅ that needs an asterisk is a ✗".

A heuristic lint for a review's status table / status lines (deep-code-review
Phase 5; see report-format.md). It surfaces CANDIDATE lines where a positive
completion status (✅ / done / exact / matches / verified / complete) co-occurs
with a hedge (if / only / once / after / unless / requires / except / assuming /
caveat / mostly / but see …) and no downgrade marker (⚠️ / ❌ / ✗ / partial /
blocked / unverified) — i.e. a claim that is only true after a non-default action,
reported green.

A second detector (issue #192) flags a positive status whose row also carries
parity vocabulary (parity / renders / restyled / screen / "matches the design" …)
yet names NO verification surface — no URL / port and no rendered sha. When more
than one tree can serve the app, a parity claim that names no surface is INVALID
(there is nothing to downgrade): it may be true about the author's tree yet false
on every surface a human opens, so this detector fires even on a ⚠️-downgraded row.
The sha test requires >= 7 hex chars with both a hex letter and a digit (so neither
a hex-looking word nor a plain number passes as a commit).

A third detector (issue #198) flags a positive status that leans on a screenshot
(screenshot / screen capture / .png) yet names none of the pixel-defect checklist
STEMS (overlap / clip / truncat / intersect / contrast / disabl / bbox / geometr) — a
screenshot proves a render happened, not that the render is correct. It fires even on
a ⚠️-downgraded row; the discriminator is the inspection stem, matched as a substring
so an inflected citation ("nothing overlapping / clipped") still exempts. That
substring match will also exempt a row that mentions "disabled"/"contrast" for an
unrelated reason — the acceptable direction for an exemption set (under-flag, never a
false alarm on a genuine inspection).

A fourth detector (issue #200) flags a positive parity claim carrying a population
quantifier (all / every / whole / "the product" / "the app" / "all pages") but no N/M
coverage fraction — a sample generalized to the whole product. It requires a
parity-context word (so "all tests pass" is spared) and fires even on a ⚠️-downgraded
row; the discriminator is the coverage fraction ("1/6", "1 of 6"), not the marker.

A fifth detector flags a findings claim for a review mode ("security 0 new", "perf: 2 findings",
"no a11y issues", "privacy clean") with no coverage entry for that mode anywhere in the file. An
entry is exactly `mode: ran (N files)` with N >= 1 or `mode: NOT RUN (reason)` (case-insensitive,
several joined by `|` or `,`). A mode that did not run has no findings count: a claim beside a
NOT RUN entry, a bare `ran`, `ran (0 files)` or a reasonless NOT RUN is flagged too, so a skipped
mode never reads as zero findings. Modes: security, perf (performance), a11y (accessibility),
privacy, reliability, correctness, ux. The claim match is wording-based, so an unlisted phrasing
slips past (under-flag); `tests` is not a mode here because "tests: 12/12" is a count, not a review.

It is an aid to human judgement, not a proof. It can over-flag a prose line that
merely contains both a status word and a conditional; a flagged line is a lead to
re-check — downgrade to partial/blocked with the condition as the headline, or
split into a scoped two-status verdict — never an automatic defect. Run it on the
status table, not the whole report, for the least noise.

It also UNDER-flags — a clean exit is never proof the claims are true, only that
no listed pattern matched. Known false negatives:
  * it scans one physical line at a time, so a status and its hedge on different
    (wrapped) lines are missed — keep each status row on a single line;
  * the downgrade suppressor is line-global, so a downgrade word used in prose
    ("no partial coverage") can silence a genuine hedged-green on that line;
  * the token lists are fixed — a completion or hedge word not listed slips past.

Exit 0 = no candidate lines (none of the five detectors fired), 1 = candidate(s)
found, 2 = usage/unreadable.
Stdlib only. Reports line numbers + the tokens matched, not full line content.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NoReturn

# A positive completion status: the claim side of "a ✅ that needs an asterisk".
POSITIVE = (
    "✅",
    "done", "exact", "exactly", "matches", "matched", "match", "verified",
    "complete", "completed",
)
# A hedge: the asterisk. A completion claim true only after one of these is a ✗.
HEDGES = (
    "caveat", "asterisk", "footnote", "mostly", "but see", "unless",
    "assuming", "provided", "as long as", "so long as", "requires",
    "once you", "after you", "after selecting", "except", "only", "if",
)
# An honest downgrade already present → the line is not the failure this catches.
# Both ⚠ code points: bare U+26A0 and U+26A0+U+FE0F (with variation selector).
DOWNGRADE = (
    "⚠️", "⚠", "❌", "✗", "partial", "blocked", "changes-requested", "unverified",
)
# UI / parity vocabulary: marks a status line as a design / parity claim, which
# must name a verification surface. A positive parity status naming no surface is
# the failure the second detector catches (issue #192 — "which tree served it?",
# ambiguous the moment more than one tree can serve the app). A broad single word
# ("screen" …) can over-flag a non-parity row ("screen-reader"); a flag is a lead.
SURFACE_VOCAB = (
    "parity", "renders", "rendered", "restyled", "restyle",
    "matches the design", "matches the reference", "looks the same", "screen",
)
# The detector flags a parity row that names NEITHER a URL / port NOR a rendered
# sha (either one present = a surface is named → no flag; issue #192's "no URL and
# no sha"). The sha needs >= 7 hex chars with BOTH a hex letter and a digit, so a
# hex-looking prose word ("defaced") and a plain number ("1234567") are neither
# mistaken for a commit; the URL needs a real host, so a time ("12:30") is not a port.
_URL_RE = re.compile(r"https?://|\blocalhost\b|\b\d{1,3}(?:\.\d{1,3}){3}\b", re.IGNORECASE)
_SHA_RE = re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{7,40}\b", re.IGNORECASE)
# Screenshot / render-artifact vocabulary: marks a UI status leaning on an image. A
# positive status that cites an image but names no inspection is the failure the third
# detector catches (issue #198 — a screenshot is an artifact, not an inspection).
SHOT_VOCAB = (
    "screenshot", "screen shot", "screencap", "screen capture", ".png",
)
# Inspection STEMS: the pixel-defect checklist a UI status cites (product-ux gate 1),
# matched as SUBSTRINGS (not word-bounded). This is an EXEMPTION set — a row that cites
# its inspection in any inflection ("no overlapping, nothing clipped") must be spared,
# and failing toward exempting is the safe direction here (unlike the claim sets, where
# the word boundary keeps "verified" out of "unverified"). "state" is deliberately NOT
# here: a shot labelled only with its data state, with no defect attestation, is exactly
# what #198 catches, so citing the state does not clear the flag.
INSPECT_STEMS = (
    "overlap", "intersect", "clip", "truncat", "contrast", "disabl",
    "bbox", "bounding", "geometr",
)
# Population quantifiers + parity context: an aggregate parity claim that names no
# coverage fraction generalizes a sample to the whole product (issue #200). The fourth
# detector fires on a positive parity claim carrying a population word but no N/M
# fraction; it fires regardless of a downgrade marker (⚠️ "the whole app matches" is as
# unscoped as the green form; the issue's honest example carries ⚠️ AND a fraction). It
# also requires a parity-context word, so "all tests pass" (no parity claim) is spared.
POP_QUANTIFIER = (
    "all", "every", "whole", "entire", "everywhere",
    "the product", "the app", "all pages", "all screens",
    # aggregate-completion phrases that generalize without a population word:
    "parity achieved", "parity complete", "port complete", "migration complete",
    "restyle complete",
)
PARITY_CTX = (
    "parity", "matches", "match", "prototype", "design", "reference",
    "screen", "page", "port", "restyle", "renders", "rendered", "looks the same",
)
# A coverage fraction (N/M or "N of M", each operand <= 2 digits and N <= M) scopes the
# claim → exempt. The operand bound and N <= M reject a slash-date ("2026/09", "28/09");
# an ambiguous small MM/DD like "09/12" can still read as a fraction — an accepted
# residual for a heuristic aid.
_FRACTION_RE = re.compile(r"\b(\d{1,2})\s*(?:/|of)\s*(\d{1,2})\b", re.IGNORECASE)


def _has_fraction(line: str) -> bool:
    """A coverage fraction present: N/M or "N of M", each <= 2 digits with N <= M."""
    return any(int(m.group(1)) <= int(m.group(2)) for m in _FRACTION_RE.finditer(line))


# Mode coverage (fifth detector): a findings claim for a review mode needs a coverage entry for it.
MODES = ("security", "perf", "performance", "a11y", "accessibility", "privacy", "reliability", "correctness", "ux")
ALIAS = {"performance": "perf", "accessibility": "a11y"}
PLACEHOLDER = {"reason", "x", "n/a", "none"}  # a template word is not a reason
_M = "|".join(MODES)
_MODE = r"\b(?:" + _M + r")\b(?![\w-])"
# an entry: `mode: ran (12 files[, 0 findings])` or `mode: NOT RUN (reason)`; a table row `| mode | ran (3 files) |` too
_COV = re.compile(r"\b(" + _M + r")\s*[:|]\s*(?:ran\s*\(\s*([\d,]+)\s+files?\b[^)]*\)|not run\s*\(([^)]*)\))", re.IGNORECASE)
_COV_HEAD = re.compile(r"\b(" + _M + r")\s*[:|]\s*(?:ran|not run)\b", re.IGNORECASE)
# a count or negation word; a bare count that is a file/line total ("12 files") is not a findings count
_TOK = r"(?:no|nothing|none|zero|clean|ok|pass(?:ed)?|clear|all|\d[\d,]*\b(?![:/-]|\.\d|\s*(?:files?|lines?|%)))"
_NOUN = r"\s*(?:findings?|issues?|concerns?|gaps?|defects?|vulns?|vulnerabilities|regressions?|problems?|risks?|errors?|bugs?)\b"
# a claim starts at the line, a bullet, or after `|` `:` `;` `,` `.` (so "we ran no security scan" is prose, not a claim)
_START = r"(?:^|[|:;,.>])\s*(?:[-+]\s+|\d+[.)]\s+)?"
_BACK = re.compile(_START + _TOK + r"\b[^|:;,.]{0,12}$", re.IGNORECASE)  # "no new security ...", "0 new security ..."
_FWD = re.compile(r"\b" + _TOK + r"\b", re.IGNORECASE)


def mode_gaps(text: str) -> list[str]:
    """Messages for findings claims about a review mode that no `ran (N files)` coverage entry backs. [] when none."""
    fence = False
    lines = []
    for line in text.splitlines():  # fenced code is quoted text, not the report's own claim; keep line numbers
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            line = ""
        lines.append("" if fence else re.sub(r"[*_]", "", line))
    cov: dict[str, set[str]] = {}
    out: list[str] = []
    for n, line in enumerate(lines, start=1):
        good = set()
        for m in _COV.finditer(line):
            mode = ALIAS.get(m[1].lower(), m[1].lower())
            if m[2] is not None and int(m[2].replace(",", "") or 0) > 0:
                cov.setdefault(mode, set()).add("ran"); good.add(m.start())
            elif m[3] is not None and m[3].strip() and m[3].strip().lower() not in PLACEHOLDER:
                cov.setdefault(mode, set()).add("not run"); good.add(m.start())
        for m in _COV_HEAD.finditer(line):
            if m.start() not in good:
                out.append(f"L{n}: malformed coverage entry for mode '{m[1].lower()}' - use \"{m[1].lower()}: ran (N files)\" "
                           f"with N >= 1, or \"{m[1].lower()}: NOT RUN (reason)\" (a real reason, not a placeholder).")
    for n, line in enumerate(lines, start=1):
        bare = _COV.sub(" ", line)  # an entry's own reason text is not a claim
        for m in re.finditer(_MODE, bare, re.IGNORECASE):
            tail = re.split(_MODE + r"|[.;](?:\s|$)", bare[m.end():], maxsplit=1, flags=re.IGNORECASE)[0]
            at_start = re.search(_START + r"$", bare[:m.start()])
            fwd = _FWD.search(tail)  # the token starts within ~28 chars of the mode word
            back = _BACK.search(bare[:m.start()]) and re.match(_NOUN, tail, re.IGNORECASE)
            if not ((at_start and fwd and fwd.start() <= 28) or back):
                continue
            mode = ALIAS.get(m[0].lower(), m[0].lower())
            if "not run" in cov.get(mode, ()):
                out.append(f"L{n}: findings claim for mode '{mode}' but its coverage entry says NOT RUN - a mode that did not run "
                           "has no findings count; report NOT RUN, never 0.")
            elif "ran" not in cov.get(mode, ()):
                out.append(f"L{n}: findings claim for mode '{mode}' with no coverage entry - add \"{mode}: ran (N files)\" or "
                           f"\"{mode}: NOT RUN (reason)\"; a skipped mode is not zero findings.")
    return out


def die(code: int, msg: str) -> NoReturn:
    print(f"validate_status_claims: {msg}", file=sys.stderr)
    raise SystemExit(code)


def find(tokens: tuple[str, ...], line_lower: str, line_raw: str) -> list[str]:
    """Return which tokens appear on the line. Emoji/phrases: substring;
    single ASCII words: word-boundary (so 'verified' does not match
    'unverified', and 'complete' does not match 'incomplete')."""
    hits: list[str] = []
    for t in tokens:
        if not t.isascii():  # emoji
            if t in line_raw:
                hits.append(t)
        elif " " in t:  # phrase (incl. the trailing-space "if ")
            if t in line_lower:
                hits.append(t.strip())
        else:  # single word
            if re.search(r"\b" + re.escape(t) + r"\b", line_lower):
                hits.append(t)
    return hits


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("--file", "-f"):
        die(2, "usage: validate_status_claims.py --file <report-or-status-table.md>")
    path = Path(argv[2])
    if not path.is_file():
        die(2, f"not a file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        die(2, "unreadable input")

    flagged: list[tuple[int, list[str], list[str]]] = []       # hedged-green
    surfaceless: list[tuple[int, list[str], list[str]]] = []   # UI/parity, no surface
    uninspected: list[tuple[int, list[str], list[str]]] = []   # screenshot, no inspection
    overscoped: list[tuple[int, list[str], list[str]]] = []    # parity claim, no N/M scope
    for n, line in enumerate(text.splitlines(), start=1):
        low = line.lower()
        pos = find(POSITIVE, low, line)
        if not pos:
            continue
        # Surfaceless-parity detector runs FIRST and regardless of a downgrade
        # marker: a parity claim that names no surface is INVALID, not merely
        # downgraded — a ⚠️ does not rescue it (report-format.md), so the downgrade
        # marker must not suppress this half.
        surf = find(SURFACE_VOCAB, low, line)
        if surf and not _URL_RE.search(line) and not _SHA_RE.search(line):
            surfaceless.append((n, pos, surf))
        # Screenshot-without-inspection detector, also regardless of a downgrade
        # marker: a UI status leaning on an image but citing no pixel-defect checklist
        # item is unverified (issue #198). The discriminator is the inspection token,
        # not the marker — a row that cites overlap/clip/contrast/... is exempt.
        shot = find(SHOT_VOCAB, low, line)
        if shot and not any(stem in low for stem in INSPECT_STEMS):
            uninspected.append((n, pos, shot))
        # Aggregate-scope detector (issue #200), also regardless of a downgrade marker:
        # a parity claim carrying a population quantifier but no N/M coverage fraction
        # generalizes a sample to the whole product. The discriminator is the fraction;
        # a parity-context word is required so "all tests pass" is not a false hit.
        pop = find(POP_QUANTIFIER, low, line)
        if pop and find(PARITY_CTX, low, line) and not _has_fraction(line):
            overscoped.append((n, pos, pop))
        # Hedged-green detector: an honest downgrade already surfaces the caveat, so
        # a downgraded line is not the failure THIS half catches.
        if find(DOWNGRADE, low, line):
            continue
        hedge = find(HEDGES, low, line)
        if hedge:
            flagged.append((n, pos, hedge))

    modegaps = mode_gaps(text)
    if flagged or surfaceless or uninspected or overscoped or modegaps:
        for n, pos, hedge in flagged:
            print(
                f"L{n}: green status {pos} carries a hedge {hedge} — "
                "downgrade (partial/blocked, condition as the headline) or split "
                "into a two-status verdict. A ✅ that needs an asterisk is a ✗."
            )
        for n, pos, surf in surfaceless:
            print(
                f"L{n}: green UI/parity status {pos} names no verification surface "
                f"(vocab {surf}) — a parity claim with no URL and no rendered sha is "
                "INVALID, not downgraded; name url · tree/worktree · branch · sha, or "
                "make no claim (#192)."
            )
        for n, pos, shot in uninspected:
            print(
                f"L{n}: green UI status {pos} leans on an image {shot} but names no "
                "inspection — cite the pixel-defect checklist (overlap / clip / "
                "contrast / disabled-looks-disabled, product-ux gate 1), or it "
                "is unverified, not verified (#198)."
            )
        for n, pos, pop in overscoped:
            print(
                f"L{n}: green parity status {pos} generalized over {pop} with no "
                "coverage fraction — scope it to the screens verified (N/M) or name the "
                "correspondence table; a claim over the product from a sample is a High "
                "communication defect (#200)."
            )
        for msg in modegaps:
            print(msg)
        total = len(flagged) + len(surfaceless) + len(uninspected) + len(overscoped) + len(modegaps)
        print(
            f"validate_status_claims: {total} line(s) to re-check "
            f"({len(flagged)} hedged-green, {len(surfaceless)} surfaceless parity, "
            f"{len(uninspected)} uninspected screenshot, {len(overscoped)} overscoped parity, "
            f"{len(modegaps)} mode coverage)"
        )
        return 1
    print("validate_status_claims: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
