#!/usr/bin/env python3
"""Placeholder precision of the privacy gate: placeholder-looking secrets pass, live-looking ones still block (both gate halves). Offline.

`@@` markers keep scanners (and GitHub push protection) off the fake tokens; they are stripped before the gate runs.
"""
import pathlib, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PASS = ["AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE", 'token = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"', "OPENAI_API_KEY=sk-REPLACE_ME_with_your_key",
        "STRIPE_KEY=sk_test_@@A2aMrXbJqxi4ai1aZSzJWHU7", "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_n91DMA5Cj6vP3w01RyvJgcjy"]
BLOCK = ["AWS_ACCESS_KEY_ID=AKIA@@MTCCOS379D7HHQPJ", "HF_TOKEN=hf_@@hf4mTfLTr1l3Ug8hEgnY2VyCFAgWRbtyX9", "DATABASE_URL=postgres://app:a0V9MzHCrx4hWx@@4nf36j@db.internal.example.com:5432/prod",
         "STRIPE_KEY=sk_live_@@n91DMA5Cj6vP3w01RyvJgcjy"]


# Real-format tokens built at runtime; a placeholder word elsewhere on the same line must not hide them.
GH, AK, SK = "ghp_" + "Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF3hJ6", "AKIA" + "MTCCOS379D7HHQPJ", "sk_live_" + "n91DMA5Cj6vP3w01RyvJgcjy"
BLOCK += [f"examples {GH}", f"csrf_token=1 token={GH}", f"{AK}  # example prod key", f"pk_live_x sk={SK}", f"NEXT_PUBLIC_API={GH}",
          f"xxxxxxxxxx 0000000000 {GH}"]


def gate(text):
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t); (t / "x.txt").write_text(text.replace("@@", "") + "\n")
        return subprocess.run(["bash", str(ROOT / "scripts/ci-gates.sh"), "privacy", "--banlist", str(ROOT / ".banlist.txt"), str(t / "x.txt")],
                              capture_output=True, text=True).returncode


for s in PASS: assert gate(s) == 0, ("placeholder blocked", s)
for s in BLOCK: assert gate(s) != 0, ("live secret passed", s)
print("secret precision: ok")
