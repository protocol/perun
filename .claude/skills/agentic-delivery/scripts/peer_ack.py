#!/usr/bin/env python3
"""peer_ack.py — read receipts for peer directives, on the coordination board: no ack within T seconds means undelivered.

A directive can vanish (wrong channel, session gone, context compacted). `new` prints a token. The sender posts the directive with
`board_post.py --type DECISION|HANDOFF|BLOCKER|QUESTION ... --token <tok>`; the post itself is the record of the expected ack, so there
is no second ledger. The recipient answers with `board_post.py --type ACK --token <tok>`: an explicit token ack, the one ACK that is not
chatter (an ACK without a token is still rejected). `undelivered --repo OWNER/NAME --issue N [--after SECONDS]` (default 600) reads the board and
prints each token-bearing directive older than the limit with no matching ACK, exit 1. When the directive names `to:`, only that agent's
ACK counts. Fail closed: a board that cannot be read (outage, torn or undecodable page, non-comment rows) is reported undelivered, exit 1.
Bad arguments exit 2. An ack proves the token was seen, not that the directive was followed.
"""
import argparse
import os
import secrets
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_common as bc  # noqa: E402


def undelivered(comments, after=600, now=None):
    """Directive posts (dicts with agent, type, fields, ts) older than `after` seconds with no matching ACK. Raises on malformed rows."""
    posts = []
    for c in comments:
        p = bc.parse_header(bc.first_line(c["body"]))
        if p and not p["errors"] and "token" in p["fields"]:
            p["ts"] = bc.parse_ts(c["created_at"]).timestamp()
            posts.append(p)
    acks = {(p["fields"]["token"], p["agent"]) for p in posts if p["type"] == "ACK"}
    t = now or time.time()
    def acked(p):
        return any(tok == p["fields"]["token"] and p["fields"].get("to", who) == who for tok, who in acks)
    return [p for p in posts if p["type"] != "ACK" and t - p["ts"] > after and not acked(p)]


def main(argv, runner=bc.default_runner, now=None):
    ap = argparse.ArgumentParser(prog="peer_ack.py", allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("new")
    u = sub.add_parser("undelivered")
    u.add_argument("--repo", required=True)
    u.add_argument("--issue", type=int, required=True)
    u.add_argument("--after", type=int, default=600)
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    if a.cmd == "new":
        print(secrets.token_hex(4))
        return 0
    if not bc.validate_repo(a.repo) or a.issue < 1 or a.after < 0:
        print("usage: --repo OWNER/NAME --issue N>0 [--after S>=0]", file=sys.stderr)
        return 2
    try:
        late = undelivered(bc.gh_list(runner, bc.comments_path(a.repo, a.issue)), a.after, now)
    except Exception as e:  # fail closed: an unreadable board proves nothing was delivered
        print(f"undelivered: board unreadable ({str(e)[:120]})")
        return 1
    for p in late:
        print(f"undelivered {p['fields']['token']} from {p['agent']}" + (f" to {p['fields']['to']}" if "to" in p["fields"] else ""))
    return 1 if late else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
