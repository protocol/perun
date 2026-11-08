"""route_auth_map.py: a caller token forwarded upstream reads auth=forwarded (INFO); a server-secret Bearer stays HIGH none. Fictional fixtures."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/route_auth_map.py"

FX = {
    "app/actions/fwd.ts": '"use server";\nimport { cookies } from "next/headers";\nexport async function saveThing(b: string) {\n  const t = cookies().get("session")?.value;\n  return fetch("https://api.example.com/x", { method: "POST", headers: { Authorization: `Bearer ${t}` }, body: b });\n}\n',
    "app/actions/key.ts": '"use server";\nexport async function spend(b: string) {\n  return fetch("https://api.example.com/x", { method: "POST", headers: { Authorization: `Bearer ${process.env.ACME_KEY}` }, body: b });\n}\n',
    "app/actions/prm.ts": '"use server";\nexport const dropTeam = async (uid: string, authToken: string) => {\n  return fetch(`https://api.example.com/t/${uid}`, { method: "DELETE", headers: { Authorization: `Bearer ${authToken}` } });\n};\n',
    "app/actions/loc.ts": '"use server";\nexport const dropAll = async (uid: string) => {\n  const authToken = process.env.ACME_KEY;\n  return fetch(`https://api.example.com/t/${uid}`, { method: "DELETE", headers: { Authorization: `Bearer ${authToken}` } });\n};\n',
    "app/actions/hlp.ts": '"use server";\nexport async function listAll(q: string, authToken?: string) {\n  return fetch(`https://api.example.com/l?${q}`, { headers: getHeader(authToken ?? "") });\n}\n',
    "app/api/a/route.ts": 'const authToken = process.env.ACME_KEY;\nconst getHeader = (t) => ({ Authorization: `Bearer ${t}` });\nexport async function POST(req: Request) {\n  return fetch("https://api.example.com/x", { method: "POST", headers: getHeader(authToken) });\n}\n',
    "app/api/b/route.ts": 'const mk = (authToken) => ({ Authorization: `Bearer ${authToken}` });\nexport async function POST(req: Request) {\n  return fetch("https://api.example.com/x", { method: "POST", headers: mk(process.env.ACME_KEY) });\n}\n',
    "app/api/c/route.ts": 'export async function POST(req) {\n  await fetch(u, { headers: { Authorization: `Bearer ${process.env.K}`, \'x-user\': req.headers.get(\'x-user\') } });\n}\n',
    "app/api/d/route.ts": 'export async function POST(req) {\n  await fetch(u, { headers: { Authorization: \'Bearer abc\' }, body: req.headers.get(\'x\') });\n}\n',
    "app/api/e/route.ts": 'export async function POST(req) {\n  const t = process.env.TOK;\n  getHeader(\'ua\');\n  await fetch(u, { headers: { Authorization: \'Bearer \' + t } });\n}\n',
    "app/api/f/route.ts": 'export async function POST(req) {\n  const t = process.env.K, u2 = req.headers.get(\'a\');\n  await fetch(u, { headers: { Authorization: `Bearer ${t}` } });\n}\n',
    "app/api/g/route.ts": 'export async function POST(req) {\n  await fetch(u, { headers: { Authorization: req.headers.get(\'a\') } });\n  await fetch(u, { headers: { Authorization: `Bearer ${process.env.K}` } });\n}\n',
    "app/api/h/route.ts": 'export async function POST(req) {\n  await fetch(u, { headers: { Authorization: `Bearer ${req.headers.get(\'a\')}:${process.env.K}` } });\n}\n',
    "app/api/i/route.ts": 'export async function POST(req) {\n  const s = process.env.K;\n  const t = s + req.headers.get(\'a\');\n  await fetch(u, { headers: { Authorization: t } });\n}\n',
    "app/api/j/route.ts": 'export async function POST(req) {\n  let t = req.headers.get(\'a\');\n  t = await vault.read(\'k\');\n  await fetch(u, { headers: { Authorization: t } });\n}\n',
    "app/api/hdr/route.ts": 'export async function POST(req: Request) {\n  const a = req.headers.get("authorization");\n  return fetch("https://api.example.com/x", { method: "POST", headers: { authorization: a } });\n}\n',
}


class T(unittest.TestCase):
    def test_rows(self):
        with tempfile.TemporaryDirectory() as d:
            for k, v in FX.items():
                p = Path(d, k); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(v)
            o = subprocess.run([sys.executable, "-I", str(SCRIPT), d], capture_output=True, text=True).stdout
        rows = [l for l in o.splitlines() if ": INFO: " in l or ": HIGH: " in l]
        want = {"app/actions/fwd": "INFO: ACTION saveThing auth=forwarded", "app/actions/key": "HIGH: ACTION spend auth=none", "app/actions/prm": "INFO: ACTION dropTeam auth=forwarded", "app/actions/loc": "HIGH: ACTION dropAll auth=none", "app/actions/hlp": "INFO: ACTION listAll auth=forwarded", "app/api/a": "HIGH: POST /api/a auth=none", "app/api/b": "HIGH: POST /api/b auth=none", "app/api/c": "HIGH: POST /api/c auth=none", "app/api/d": "HIGH: POST /api/d auth=none", "app/api/e": "HIGH: POST /api/e auth=none", "app/api/f": "HIGH: POST /api/f auth=none", "app/api/g": "HIGH: POST /api/g auth=none", "app/api/h": "HIGH: POST /api/h auth=none", "app/api/i": "HIGH: POST /api/i auth=none", "app/api/j": "HIGH: POST /api/j auth=none", "app/api/hdr": "INFO: POST /api/hdr auth=forwarded"}
        self.assertEqual(len(rows), 16, o)
        for k, w in want.items():
            self.assertTrue(any(l.startswith(k) and w in l for l in rows), (k, o))


if __name__ == "__main__":
    unittest.main()
