#!/usr/bin/env python3
"""Compatibility shim: the decision council is now Veche (`veche.py`).

Importing this module re-exports Veche's public names (run, cite_state, parse, fence, main, ...) and runs nothing.
Run as a script it forwards every argument to Veche's CLI, so its exit code (0, 3 or 4) and output are exactly Veche's.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from veche import *  # noqa: E402,F401,F403
from veche import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
