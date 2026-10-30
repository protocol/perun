#!/usr/bin/env python3
"""parity_differ's focus_gate accept-trust route must call focus_gate.load_record with the arguments it defines, and
`_focus_gate()` must load focus_gate.py on every Python.

FocusGateRoute imports focus_gate normally and hands it to parity_differ. RealFocusGateLoad leaves `_focus_gate()`
unpatched in the state a fresh interpreter starts in (focus_gate not yet in sys.modules). There the loader used to skip
registering the module, so on Python 3.12 and 3.14 its dataclasses failed to build and the loader fell back to the
`git log` route while 3.15 loaded focus_gate: the owner check ran a different route per Python. Throwaway git repos, no
network."""
import importlib.util
import os
import subprocess
import sys
import tempfile
import types
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

SKILLS = Path(__file__).resolve().parent.parent / ".claude/skills"
sys.path.insert(0, str(SKILLS / "agentic-delivery/scripts"))
import focus_gate as fg  # noqa: E402

spec = importlib.util.spec_from_file_location("parity_differ", SKILLS / "deep-code-review/scripts/parity_differ.py")
pd = importlib.util.module_from_spec(spec)
sys.modules["parity_differ"] = pd
spec.loader.exec_module(pd)

OWNER, AGENT = "owner@example.com", "lane-bot@example.com"


class FocusGateRoute(unittest.TestCase):
    gate = fg   # what `pd._focus_gate()` returns here; None leaves the real loader in place (RealFocusGateLoad)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pd-focus-gate-")
        self.addCleanup(tmp.cleanup)
        self.repo = tmp.name
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}   # never a caller's GIT_DIR or author
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", DCR_OWNER_EMAIL=OWNER)
        patches = [mock.patch.dict(os.environ, env, clear=True)]
        if self.gate is not None:
            patches.append(mock.patch.object(pd, "_focus_gate", return_value=self.gate))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.git("init", "-q")

    def git(self, *args, **env):
        subprocess.run(["git", "-C", self.repo, *args], check=True, capture_output=True, env={**os.environ, **env})

    def commit(self, email, body="row\n"):
        """Commit accept.tsv as `email`; return its path."""
        path = Path(self.repo, "accept.tsv")
        path.write_text(body)
        self.git("add", "accept.tsv")
        self.git("-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "chore: accept",
                 GIT_AUTHOR_NAME="Jane Smith", GIT_AUTHOR_EMAIL=email,
                 GIT_COMMITTER_NAME="Jane Smith", GIT_COMMITTER_EMAIL=email)
        return str(path)

    def test_owner_authored_file_is_trusted(self):
        text, source, err = pd.read_owner_authored(self.commit(OWNER))
        self.assertEqual((text, err), ("row\n", None))
        self.assertTrue(source.startswith("owner-commit "), source)

    def test_agent_authored_file_is_refused(self):
        text, source, err = pd.read_owner_authored(self.commit(AGENT))
        self.assertEqual((text, source), (None, None))
        self.assertIn("is not the owner", err)

    def test_no_owner_configured_is_refused(self):
        path = self.commit(OWNER)
        del os.environ["DCR_OWNER_EMAIL"]
        text, source, err = pd.read_owner_authored(path)
        self.assertEqual((text, source), (None, None))
        self.assertIn("no owner email configured", err)


class RealFocusGateLoad(FocusGateRoute):
    """The route above through the real `pd._focus_gate()`; the inherited owner-trusted case is the end-to-end run
    (with no `rev`, only the focus_gate route trusts the file, and its source reads `owner-commit`)."""
    gate = None

    def setUp(self):
        modules = mock.patch.dict(sys.modules)   # whatever the loader registers is dropped again afterwards
        modules.start()
        self.addCleanup(modules.stop)
        for name in ("focus_gate", "refix_gate"):
            sys.modules.pop(name, None)   # as in a fresh interpreter, where the loader's own registration must do
        pd._focus_gate.cache_clear()
        self.addCleanup(pd._focus_gate.cache_clear)
        super().setUp()

    def test_loader_returns_and_registers_the_module(self):
        module = pd._focus_gate()
        self.assertIsNotNone(module)
        self.assertIs(sys.modules.get("focus_gate"), module)

    def test_loaded_module_is_reused_only_for_the_same_file(self):
        sys.modules["focus_gate"] = fg
        self.assertIs(pd._focus_gate(), fg)
        pd._focus_gate.cache_clear()
        other = sys.modules["focus_gate"] = types.SimpleNamespace(__file__="/elsewhere/focus_gate.py")
        module = pd._focus_gate()
        self.assertIsNot(module, other)
        self.assertTrue(hasattr(module, "load_record"))

    def test_failed_import_falls_back_and_leaves_no_entry(self):
        with mock.patch.object(SourceFileLoader, "exec_module", side_effect=RuntimeError("broken")):
            self.assertIsNone(pd._focus_gate())
        self.assertNotIn("focus_gate", sys.modules)


if __name__ == "__main__":
    unittest.main()
