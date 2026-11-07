"""route_auth_map.py false-positive cuts: Member/Account identity guards, and a handler that answers 401 itself. Fictional fixtures (Acme, example.com)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/route_auth_map.py"

FX = {
    "app/api/m/route.ts": 'import { requireMember } from "@/acme/guards";\nexport async function POST(req: Request) {\n  const m = await requireMember(req);\n  if (m instanceof Response) return m;\n  return Response.json({ ok: true });\n}\n',
    "server.js": 'const express = require("express");\nconst app = express();\napp.post("/acct", withMember, (req, res) => {\n  if (!req.member) return res.status(401).json({});\n  res.json({ ok: true });\n});\napp.post("/acct2", (req, res) => {\n  if (!req.member) return res.sendStatus(401);\n  res.json({ ok: true });\n});\n',
    "app/api/bff/route.ts": 'import { NextResponse } from "next/server";\nexport async function POST(req: Request) {\n  const h = resolveAuthHeader(req);\n  if (!h) return NextResponse.json({ error: "no" }, { status: 401 });\n  return fetch("https://api.example.com/x", { method: "POST", headers: { authorization: h } });\n}\n',
    "opt.js": 'const express = require("express");\nconst app = express();\napp.post("/opt", withMember, (req, res) => {\n  res.json({ ok: true });\n});\n',
    "app/api/hdr/route.ts": 'export async function POST(req: Request) {\n  if (!req.headers.get("x-user-id")) return Response.json({}, { status: 401 });\n  return Response.json({ uid: req.headers.get("x-user-id") });\n}\n',
    "app/api/trust/route.ts": 'export async function POST(req: Request) {\n  if (!req.headers.authorization) return Response.json({}, { status: 401 });\n  return Response.json({ a: req.headers.authorization });\n}\n',
    "app/api/open/route.ts": 'export async function POST(req: Request) {\n  const body = await req.json();\n  return Response.json({ n: body.n });\n}\n',
    "app/api/lit/route.ts": 'export async function POST(req: Request) {\n  const b = await req.json();\n  if (b.bad) return Response.json({}, { status: 401 });\n  const m = "authorization: none";\n  return Response.json({ m });\n}\n',
    "resset.js": 'const express = require("express");\nconst app = express();\napp.post("/echo", (req, res) => {\n  if (!req.headers.authorization) return res.status(401).end();\n  res.set("authorization", req.headers.authorization);\n  res.json({ ok: true });\n});\n',
    "middleware.ts": 'import { NextResponse } from "next/server";\nexport function middleware(req: Request) {\n  return NextResponse.json({}, { status: 401 });\n}\nexport const config = { matcher: ["/api/admin/:path*"] };\n',
    "app/api/admin/lock/route.ts": 'export async function POST(req: Request) {\n  if (!req.headers.get("x-user-id")) return Response.json({}, { status: 401 });\n  return Response.json({ ok: true });\n}\n',
}


class T(unittest.TestCase):
    def test_rows(self):
        with tempfile.TemporaryDirectory() as d:
            for k, v in FX.items():
                p = Path(d, k); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(v)
            o = subprocess.run([sys.executable, "-I", str(SCRIPT), d], capture_output=True, text=True).stdout
        rows = [l for l in o.splitlines() if ": INFO: " in l or ": HIGH: " in l]
        self.assertTrue(rows, o)
        want = {"app/api/open/": "HIGH: POST /api/open auth=none", "opt.js": "HIGH: POST /opt auth=none", "app/api/hdr/": "HIGH: POST /api/hdr auth=presence-check", "app/api/trust/": "HIGH: POST /api/trust auth=presence-check",
                "app/api/admin/": "INFO: POST /api/admin/lock auth=middleware", "app/api/bff/": "INFO: POST /api/bff auth=presence-check", "app/api/lit/": "HIGH: POST /api/lit auth=presence-check", "resset.js": "HIGH: POST /echo auth=presence-check"}  # optional withMember never refuses; a presence 401 is HIGH unless it forwards Authorization (a string literal or res.set is no forward)
        self.assertEqual(len(rows), 11, o)
        for l in rows:
            k = next((k for k in want if l.startswith(k)), None)
            self.assertTrue(k is None or want[k] in l, l)
            self.assertTrue(k is not None or ": INFO: " in l, l)  # requireMember / req.member rows stay INFO
        self.assertEqual(sum(1 for l in rows if ": HIGH: " in l), 6, o)


if __name__ == "__main__":
    unittest.main()
