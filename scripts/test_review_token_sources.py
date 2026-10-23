#!/usr/bin/env python3
"""Test for review_token_sources.py on a synthetic transcript (no real data). Exit 1 on failure."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_token_sources as r  # noqa: E402


def row(role, *blocks):
    return json.dumps({"type": role, "message": {"content": list(blocks)}})


def use(i, name, **inp):
    return {"type": "tool_use", "id": i, "name": name, "input": inp}


def res(i, text):
    return {"type": "tool_result", "tool_use_id": i, "content": text}


rows = [
    row("user", res("x0", "z" * 9999)),  # before invocation: ignored
    row("assistant", use("a", "Skill", skill="deep-code-review")),
    row("user", res("a", "s" * 400)),
    row("assistant", use("b", "Read", file_path="/p/skills/deep-code-review/SKILL.md")),
    row("user", res("b", "r" * 400)),
    row("assistant", use("c", "Read", file_path="/p/app.py")),
    row("user", res("c", "c" * 4000)),
    row("assistant", use("d", "Bash", command="grep -rn foo .")),
    row("user", res("d", "g" * 800)),
    row("assistant", use("e", "Bash", command="git diff")),
    row("user", res("e", "b" * 2000)),
    row("assistant", {"type": "text", "text": "t" * 400}, {"type": "thinking", "thinking": "k" * 100}),
    row("assistant", use("f", "Grep", pattern="p")),
    row("user", res("f", [{"type": "text", "text": "l" * 300}])),  # list-content tool_result
]
other = [row("user", res("q", "n" * 5000))]  # session that never invoked the skill: excluded

with tempfile.TemporaryDirectory() as d:
    (Path(d) / "a.jsonl").write_text("\n".join(rows) + "\n")
    (Path(d) / "b.jsonl").write_text("\n".join(other) + "\n")
    got = r.session(Path(d) / "a.jsonl")
    assert r.session(Path(d) / "b.jsonl") is None
assert got["skill_refs"] == 800, got
assert got["read"] == 4000 and got["bash"] == 2000, got
# text 400 + thinking 100 + tool-call inputs (JSON-encoded, measured with r.size)
inputs = [{"skill": "deep-code-review"}, {"file_path": "/p/skills/deep-code-review/SKILL.md"}, {"file_path": "/p/app.py"},
          {"command": "grep -rn foo ."}, {"command": "git diff"}, {"pattern": "p"}]
assert got["model_output"] == 500 + sum(r.size(i) for i in inputs), got
assert got["grep_glob"] == 800 + r.size([{"type": "text", "text": "l" * 300}]), got
print("PASS review_token_sources")
