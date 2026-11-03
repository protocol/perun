#!/usr/bin/env python3
"""Regression tests for dependency_currency.py: Cargo workspace members pair with the ancestor Cargo.lock, and the endoflife.date
"latest" rule (newest live LTS cycle, else newest live cycle) applies to every product, not a hardcoded list."""
import importlib.util, os, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("dc", os.path.join(HERE, "..", ".claude/skills/deep-code-review/scripts/dependency_currency.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)
TODAY = "2026-11-03"

LOCK = '[[package]]\nname = "fict-serde"\nversion = "1.0.1"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n'


class G5(unittest.TestCase):
    def test_cargo_workspace_member_drift(self):
        """A member manifest drifts against the root Cargo.lock; `dep.workspace = true` takes the root [workspace.dependencies] spec."""
        files = {"Cargo.toml": '[workspace]\nmembers = ["crates/x"]\n[workspace.dependencies]\nfict-serde = "2.0"\n',
                 "Cargo.lock": LOCK, "crates/x/Cargo.toml": '[dependencies]\nfict-serde.workspace = true\n'}
        with tempfile.TemporaryDirectory() as d:
            for f, t in files.items():
                os.makedirs(os.path.dirname(os.path.join(d, f)), exist_ok=True)
                with open(os.path.join(d, f), "w") as fh:
                    fh.write(t)
            _, rows = dc.collect(d, sorted(files), TODAY)
        self.assertTrue(any("crates/x/Cargo.toml" in str(r) and "drift" in str(r) and "fict-serde" in str(r) for r in rows), rows)

    def test_eol_latest_rule_any_product(self):
        """A product outside the old hardcoded set picks the newest live LTS cycle over a newer non-LTS one; no LTS -> newest live."""
        cs = [{"cycle": "9", "eol": False, "latest": "9.1", "lts": False}, {"cycle": "8", "eol": "2030-01-01", "latest": "8.4", "lts": "2025-01-01"},
              {"cycle": "7", "eol": "2020-01-01", "latest": "7.9", "lts": True}]
        with mock.patch.object(dc, "cycles", lambda p, t: cs):
            self.assertEqual(dc.eol_check("fictprod", "8.1", TODAY)[3:], ("8.4", "8"))
            cs2 = [dict(c, lts=False) for c in cs]
            with mock.patch.object(dc, "cycles", lambda p, t: cs2):
                self.assertEqual(dc.eol_check("fictprod", "8.1", TODAY)[3:], ("9.1", ""))

    def test_framework_ignores_lts(self):
        """A framework product with an lts-dated older cycle still reports the newest live cycle."""
        cs = [{"cycle": "20", "eol": "2030-01-01", "latest": "20.3", "lts": False}, {"cycle": "19", "eol": "2029-01-01", "latest": "19.9", "lts": "2025-01-01"}]
        with mock.patch.object(dc, "cycles", lambda p, t: cs):
            self.assertEqual(dc.eol_check("angular", "19.1", TODAY)[3:], ("20.3", ""))

    def test_cargo_excluded_or_non_workspace_member_no_rows(self):
        """A member listed in `exclude`, or under a root without [workspace], is not paired with the ancestor lock."""
        for root in ('[workspace]\nmembers = ["crates/*"]\nexclude = ["fuzz"]\n', '[package]\nname = "r"\n'):
            files = {"Cargo.toml": root, "Cargo.lock": LOCK, "fuzz/Cargo.toml": '[dependencies]\nfict-serde = "2.0"\n'}
            with tempfile.TemporaryDirectory() as d:
                for f, t in files.items():
                    os.makedirs(os.path.dirname(os.path.join(d, f)), exist_ok=True)
                    with open(os.path.join(d, f), "w") as fh:
                        fh.write(t)
                _, rows = dc.collect(d, sorted(files), TODAY)
            self.assertFalse(any("fuzz/Cargo.toml" in str(r) for r in rows), rows)


if __name__ == "__main__":
    unittest.main()
