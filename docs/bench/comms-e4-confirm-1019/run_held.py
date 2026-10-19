#!/usr/bin/env python3
"""Runs the r2 held-out arms through r1's driver (generate, read, grade; cached, never overwritten). usage: run_held.py ARM.."""
import sys
sys.dont_write_bytecode = True
import fabjudge as f  # noqa: E402

if __name__ == "__main__":
    f.b.run("held", sys.argv[1:])
