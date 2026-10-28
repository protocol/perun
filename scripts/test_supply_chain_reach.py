#!/usr/bin/env python3
"""supply_chain_check.sh reach tags: fake osv-scanner + tiny fixture tree, no network.
Run: python3 scripts/test_supply_chain_reach.py"""
import json, os, pathlib, shutil, subprocess, tempfile, unittest

SC = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/supply_chain_check.sh"
NPM = ["impkg", "@sc/imp", "devpkg", "devonly", "transpkg", "nmonly", "btick", "astropkg", "vendpkg", "rootvend", "prodgrp"]
ECO = {**{n: "npm" for n in NPM}, "Pyd": "PyPI"}


def osv(names):
    return json.dumps({"results": [{"packages": [
        {"package": {"name": n, "version": "1.0.0", "ecosystem": ECO[n]}, "groups": [],
         **({"dependency_groups": ["dev"]} if n == "prodgrp" else {}),  # osv says dev, the lock says prod: lock wins
         "vulnerabilities": [{"id": "GHSA-" + n.strip("@").replace("/", "-"), "database_specific": {"severity": "CRITICAL"}}]}
        for n in names]}]})


class Reach(unittest.TestCase):
    def setUp(self):
        t = self.t = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, t)
        (t / "bin").mkdir()
        (t / "bin/osv-scanner").write_text("#!/bin/sh\ncat '%s'\n" % (t / "osv.json"))
        (t / "bin/osv-scanner").chmod(0o755)
        r = t / "repo"
        for d in ("src/vendor", "node_modules/x", "vendor"): (r / d).mkdir(parents=True)
        (r / "src/app.js").write_text("import a from 'impkg/sub';\nconst b = await import(\"@sc/imp/x\");\nimport './local.js';\n")
        (r / "src/t.js").write_text("require('devpkg')\n")  # imported beats dev-only
        (r / "src/b.js").write_text("const c = require(`btick`)\n")  # backtick string
        (r / "src/p.astro").write_text("---\nimport x from 'astropkg'\n---\n")
        (r / "src/vendor/v.js").write_text("require('vendpkg')\n")  # nested vendor is app code
        (r / "vendor/r.js").write_text("require('rootvend')\n")  # root vendor is pruned
        (r / "node_modules/x/i.js").write_text("require('nmonly')\n")  # node_modules never counts
        self.lock(devpkg=True, devonly=True)

    def lock(self, **dev):
        pk = {"node_modules/" + n: {"version": "1.0.0", **({"dev": True} if dev.get(n) else {})} for n in NPM}
        (self.t / "repo/package-lock.json").write_text(json.dumps({"packages": pk}))

    def run_check(self, names, strict=False):
        (self.t / "osv.json").write_text(osv(names))
        env = {**os.environ, "PATH": "%s:%s" % (self.t / "bin", os.environ["PATH"])}
        env.pop("SUPPLY_CHAIN_STRICT", None)
        if strict: env["SUPPLY_CHAIN_STRICT"] = "1"
        r = subprocess.run(["bash", str(SC), "--online", "--allow-skip", "--fail-on", "high", str(self.t / "repo")],
                           capture_output=True, text=True, env=env)
        return r.returncode, r.stdout

    @staticmethod
    def row(out, name):
        return next(ln for ln in out.splitlines() if (name + "@") in ln)

    def test_tags(self):
        rc, out = self.run_check(list(ECO))
        self.assertEqual(rc, 1, out)
        for n in ("impkg", "@sc/imp", "devpkg", "btick", "astropkg", "vendpkg", "Pyd"):  # Pyd: PyPI without dev group -> fail closed
            self.assertNotIn("(reach:", self.row(out, n), n)
        self.assertIn("(reach: dev-only)", self.row(out, "devonly"))
        for n in ("transpkg", "nmonly", "rootvend", "prodgrp"):
            self.assertIn("(reach: transitive)", self.row(out, n), n)
        self.assertIn("1 dev-only", out)

    def test_only_dev_only_skips_gate_unless_strict(self):
        rc, out = self.run_check(["devonly"])
        self.assertEqual((rc, "critical=1" in out), (0, True), out)
        rc, out = self.run_check(["devonly"], strict=True)
        self.assertEqual(rc, 1, out)
        self.assertNotIn("dev-only:", out)

    def test_transitive_still_gates(self):
        rc, out = self.run_check(["transpkg", "prodgrp"])
        self.assertEqual(rc, 1, out)

    def test_lockfile_v1_fails_closed(self):
        (self.t / "repo/package-lock.json").write_text(json.dumps({"lockfileVersion": 1, "dependencies": {}}))
        rc, out = self.run_check(["devonly"])
        self.assertEqual(rc, 1, out)
        self.assertNotIn("(reach:", out)

    def test_bad_lockfile_fails_closed(self):
        (self.t / "repo/package-lock.json").write_text("{not json")
        rc, out = self.run_check(["devonly"])
        self.assertEqual(rc, 1, out)
        self.assertNotIn("(reach:", out)


if __name__ == "__main__":
    unittest.main()
