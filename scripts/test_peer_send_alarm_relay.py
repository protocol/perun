"""Pins the fire-and-forget peer-send rule and the read-before-relay alarm rule, and their eval cases."""
import json
import pathlib
import unittest

S = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills"


def read(p):
    return " ".join((S / p).read_text(encoding="utf-8").split())


def ids(p):
    return {e["id"] for e in json.loads((S / p).read_text(encoding="utf-8"))["evals"]}


class T(unittest.TestCase):
    def test_peer_send(self):
        self.assertIn("no read receipt", read("agentic-ceo/SKILL.md"))
        self.assertIn("multi-session-coordination.md", read("agentic-ceo/SKILL.md"))
        self.assertIn("fire-and-forget", read("agentic-delivery/references/multi-session-coordination.md"))
        mp = read("agentic-delivery/references/multi-session-coordination.md")
        self.assertIn("keeps the token ACK", mp)  # scoped against the board-ACK rule, which wins
        self.assertIn("../agentic-delivery/references/multi-session-coordination.md", read("agentic-ceo/SKILL.md"))
        self.assertIn("remote-peer-send-verify-from-trail", ids("agentic-ceo/evals/evals.json"))

    def test_alarm_relay(self):
        self.assertIn("last 2 comments or events", read("agentic-delivery/references/incident-response.md"))
        self.assertIn("read-subject-before-relaying-alarm", ids("agentic-delivery/evals/evals.json"))


if __name__ == "__main__":
    unittest.main()
