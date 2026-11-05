import Router from '@koa/router'
import { Agent } from 'undici'
import { randomUUID } from 'node:crypto'
import { bearer, cookie, isAdmin, ownedOr404 } from './auth.js'
import { CACHE, ROWS, SESSIONS, openSession } from './store.js'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, limit, loginLimit, same, undiciFetch, vfetch } from './util.js'

const r = new Router()
const g = new Router()
g.use(bearer, limit)

const seedDingle = [{ name: 'Jane Smith', email: 'jane@example.com', ssn: '987-65-4321', dob: '1984-03-09' }] // @@T positive pii_data seed staff list holds a plaintext national id and birth date

r.get('/api/knoll/recent', async (ctx) => { // @@R GET /api/knoll/recent 0 ; T positive missing_authn handler is registered with no authentication and lists internal rows to anyone
  ctx.body = Object.values(ROWS).map((x) => ({ id: x.id, label: x.label }))
})

g.post('/api/ext/prism/lookup-tool', async (ctx) => { // @@R POST /api/ext/prism/lookup-tool 1
  const body = ctx.request.body
  ctx.body = { reply: await askTool(`{"tool": "lookup", "arg": "${body.arg}"}`) } // @@T positive prompt_injection request value formatted into raw tool-call JSON
})

r.get('/api/ext/dingle/sample', bearer, async (ctx) => { // @@R GET /api/ext/dingle/sample 1
  ctx.body = { count: seedDingle.length }
})

g.post('/api/ext/lavender/lookup-tool', async (ctx) => { // @@R POST /api/ext/lavender/lookup-tool 1
  ctx.body = { reply: await askTool(JSON.stringify({ tool: 'lookup', arg: String(ctx.request.body.sku ?? '') })) } // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
})

g.get('/api/ext/sage/:id/image', async (ctx) => { // @@R GET /api/ext/sage/:id/image 1
  if (!/^[0-9]+$/.test(ctx.params.id)) ctx.throw(400)
  const resp = await vfetch(`https://img.vendor.example.com/p/${ctx.params.id}.jpg`, { redirect: 'error' }) // @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id with redirects off
  ctx.type = 'image/jpeg'
  ctx.body = Buffer.from(await resp.arrayBuffer())
})

r.get('/api/lantern/list', bearer, async (ctx) => { // @@R GET /api/lantern/list 1 ; T decoy missing_authn handler requires a session and the list is filtered by the session owner
  ctx.body = Object.values(ROWS).filter((x) => x.owner === ctx.state.user.uid)
})

r.post('/web/ext/flint/phone', cookie, async (ctx) => { // @@R POST /web/ext/flint/phone 1
  if (!same(ctx.get('x-csrf-token'), ctx.state.user.csrf)) ctx.throw(403) // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
  ctx.body = { updated: String(ctx.request.body.phone ?? '').length <= 20 }
})

r.post('/auth/reed-join', async (ctx) => { // @@R POST /auth/reed-join 0 public
  const newId = Math.floor(Math.random() * 1_000_000)
  console.info(`join user=${newId}`) // @@T decoy pii_log only the generated numeric id is logged
  ctx.status = 201
})

export default [r, g]
