#!/usr/bin/env python3
"""Amendment A2 (AMENDMENT2.md): bench.py's invented-figure token extractor with two fixes, applied by patching bench._numbers.
usage: fixed.py report SPLIT ARM..   (BASE=V0 env). Import this module before scoring; bench.py itself stays frozen."""
import re, sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench as b

DAY = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)(?:day|sday|nesday|rsday|urday)?\b")


def numbers(t):
    """Numeric tokens and weekdays (3-letter prefix, so Thu = Thursday) of a text; numbered-list markers are dropped BEFORE whitespace collapses."""
    t = re.sub(r"(?m)^\s*(?:[-*]\s*)?\d+[.)]\s", " ", t.lower())
    t = b.norm(t)
    return set(re.findall(r"\d+(?:\.\d+)?", t)) | set(DAY.findall(t))


b._numbers = numbers

if __name__ == "__main__":
    if sys.argv[1] == "report":
        b.report(sys.argv[2], sys.argv[3:], __import__("os").environ.get("BASE", "V0"))
