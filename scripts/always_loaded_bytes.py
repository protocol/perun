#!/usr/bin/env python3
"""Bytes put into every session, per source (bytes/4 is the token estimate), measured over every skill directory in
this repo and every command, plus the SessionStart hook of the delivery operating layer. That set is no single
install: `--full` alone (delivery, critic, comms) leaves out the skills that need their own `--with-*` flag, a
review-only install (deep-code-review only, no hooks) loads a subset, and opt-in hooks such as
`--with-terse-replies` add SessionStart text this script does not measure.

Sources (UTF-8 bytes, deterministic, no network):
  skill_descriptions    `name` + folded `description:` of every .claude/skills/*/SKILL.md (the host lists both
                        in every session); same folding as scripts/trigger_coverage.py.
  command_descriptions  `description:` of every commands/*.md.
  sessionstart_hooks    stdout of the unconditional SessionStart hook (session_brief.py, which always injects
                        HOST_RULES) run against an empty temp project with a throwaway HOME, plus
                        handoff_inject.py (empty without a .claude/handoff*.md). The UserPromptSubmit hooks
                        (context_nudge, ceo_altitude_guard, outcome_claim_guard, landing_watchdog) print only
                        when their condition fires and perun_auto_update prints nothing, so they add 0 to a
                        clean session and are not run here (landing_watchdog and perun_auto_update touch the
                        network).

Usage: always_loaded_bytes.py [ROOT]   prints one line per source, per-item detail, then `total`.
Exit 0; side effects: runs two hook scripts in a temp dir (removed afterwards).
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from trigger_coverage import description  # noqa: E402

HOOKS = ("session_brief.py", "handoff_inject.py")


def _b(s):
    return len(s.encode("utf-8"))


def skill_items(root):
    out = []
    for f in sorted(glob.glob(os.path.join(root, ".claude/skills/*/SKILL.md"))):
        name = f.split(os.sep)[-2]
        out.append((name, _b(name) + _b(description(Path(f).read_text(encoding="utf-8")))))
    return out


def command_items(root):
    out = []
    for f in sorted(glob.glob(os.path.join(root, "commands/*.md"))):
        m = re.search(r"^description:\s*(.*)$", Path(f).read_text(encoding="utf-8").split("---")[1], re.M)
        if not m:
            raise ValueError(f"{f}: no single-line `description:` in frontmatter")
        out.append(("/" + os.path.basename(f)[:-3], _b(m.group(1).strip())))
    return out


def hook_items(root):
    scripts = os.path.join(root, ".claude/skills/agentic-delivery/scripts")
    out = []
    with tempfile.TemporaryDirectory(prefix="always-loaded-") as tmp:
        env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp, "CLAUDE_PROJECT_DIR": tmp, "XDG_CACHE_HOME": tmp}
        for h in HOOKS:
            r = subprocess.run([sys.executable, os.path.join(scripts, h)], input='{"source":"startup"}', cwd=tmp,
                               env=env, capture_output=True, text=True, timeout=30)
            if r.returncode:
                raise RuntimeError(f"{h} exited {r.returncode}: {r.stderr.strip()[:200]}")
            text = r.stdout
            try:  # the host adds hookSpecificOutput.additionalContext to context, not the JSON envelope
                text = json.loads(text)["hookSpecificOutput"]["additionalContext"] if text.strip() else ""
            except (ValueError, KeyError):
                pass
            out.append((h, _b(text)))
    return out


def measure(root):
    return {"skill_descriptions": skill_items(root), "command_descriptions": command_items(root),
            "sessionstart_hooks": hook_items(root)}


def main(argv):
    root = os.path.abspath(argv[0]) if argv else os.path.dirname(HERE)
    data = measure(root)
    total = 0
    for src, items in data.items():
        s = sum(n for _, n in items)
        total += s
        print(f"{src} {s}")
        for k, n in items:
            print(f"  {k} {n}")
    print(f"total {total} (~{total // 4} tokens at bytes/4)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
