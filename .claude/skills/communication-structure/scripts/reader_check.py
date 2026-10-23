#!/usr/bin/env python3
"""Reader-accuracy check: can a reader answer fixed factual questions from a message alone?

Usage: reader_check.py --checks evals/reader-checks.json --id held02 --file message.md
Prints "<passed>/<total>" and each failed question; exit 0 = all pass, 1 = some fail,
2 = bad input (unknown id, missing file, malformed question or regex), message on stderr.

score(message, questions) -> (passed, total, failed_question_texts)
  A question passes when its target text is at most "max_words" words (when set) and
  EVERY regex in its "all" list matches it. Regexes are case-sensitive; write (?i) to
  relax one. Target by "scope": "lead" = first non-empty line, "top" = first three
  non-empty lines, "all" = the whole message. Keys are verbatim source facts with
  alternations for paraphrase; polarity is keyed on the consequence phrase.
  Not echo-only: the word cap makes a raw notes dump (longer than any message) match
  nothing, so the source text alone scores 0 (tested). Empty message passes nothing;
  empty question list is 0/0. Raises KeyError/re.error on a malformed question.
  Side effects: none.
"""
import argparse, json, re, sys
from pathlib import Path


def score(message, questions):
    lines = [l for l in message.splitlines() if l.strip()]
    target = {"lead": "\n".join(lines[:1]), "top": "\n".join(lines[:3]), "all": message}
    failed = []
    for q in questions:
        t = target[q["scope"]]
        if len(t.split()) > q.get("max_words", 10**9) or not all(re.search(k, t, re.S) for k in q["all"]):
            failed.append(q["q"])
    return len(questions) - len(failed), len(questions), failed


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--checks", required=True)
    a.add_argument("--id", required=True)
    a.add_argument("--file", required=True)
    n = a.parse_args()
    try:
        c = [x for x in json.loads(Path(n.checks).read_text()) if x["id"] == n.id]
        if not c:
            raise ValueError(f"unknown id {n.id}")
        msg = Path(n.file).read_text()
        p, t, failed = score(msg, c[0]["questions"])
    except (OSError, ValueError, KeyError, TypeError, re.error) as e:
        print(f"reader_check: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(f"{p}/{t}")
    for q in failed:
        print("FAIL:", q)
    return 0 if p == t else 1


if __name__ == "__main__":
    sys.exit(main())
