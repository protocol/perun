#!/usr/bin/env python3
"""gh_rest.fallback must return the response body only, even when a proxy's CONNECT reply precedes the real
response in `curl -i` output (as in the macOS sandbox). Offline: subprocess.run is stubbed."""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"))
import gh_rest  # noqa: E402

TLS = "x509: OSStatus -26276"


def fake(stdout):
    return mock.patch.object(gh_rest.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout, ""))


class ProxyHeaders(unittest.TestCase):
    def call(self, stdout):
        with fake(stdout), mock.patch.object(gh_rest, "_token", lambda: "t"):
            return gh_rest.fallback(["gh", "api", "repos/o/r"], 1, "", TLS)

    def test_proxy_connect_block_is_skipped(self):
        out = 'HTTP/1.1 200 Connection established\n\nHTTP/2 200 \ncontent-type: application/json\n\n{"a": 1}'
        self.assertEqual(self.call(out), (0, '{"a": 1}', ""))

    def test_direct_response_unchanged(self):
        self.assertEqual(self.call('HTTP/2 200 \ncontent-type: x\n\n{"a": 1}'), (0, '{"a": 1}', ""))


if __name__ == "__main__":
    unittest.main()
