import Router from '@koa/router'
import { Agent } from 'undici'
import { randomUUID } from 'node:crypto'
import { bearer, cookie, isAdmin, ownedOr404 } from './auth.js'
import { CACHE, ROWS, SESSIONS, openSession } from './store.js'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, limit, loginLimit, same, undiciFetch, vfetch } from './util.js'

const r = new Router()
const g = new Router()
g.use(bearer, limit)

r.get('/web/ext/trout/remember', cookie, async (ctx) => { // @@R GET /web/ext/trout/remember 1
  ctx.cookies.set('sid', openSession(ctx.state.user.uid, ctx.state.user.role), { httpOnly: false }) // @@T positive cookie_flags session cookie issued with no secure httpOnly or sameSite option
  ctx.status = 204
})

r.get('/api/basalt/:id', bearer, async (ctx) => { // @@R GET /api/basalt/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
  const row = ROWS[ctx.params.id]
  if (!row) ctx.throw(404)
  ctx.body = row
})

g.post('/api/ext/moss/push', async (ctx) => { // @@R POST /api/ext/moss/push 1
  const resp = await undiciFetch(`${VENDOR}/v1/moss`, { method: 'POST', headers: { 'X-Api-Key': VENDOR_KEY }, dispatcher: new Agent({ connect: { rejectUnauthorized: false } }), signal: AbortSignal.timeout(5000) }) // @@T positive tls_off client disables certificate verification for the vendor request
  ctx.body = { status: resp.status }
})

g.get('/api/ext/ember/fetch', async (ctx) => { // @@R GET /api/ext/ember/fetch 1
  const resp = await vfetch(String(ctx.query.url ?? '')) // @@T positive ssrf caller-supplied URL fetched from the server
  ctx.body = await resp.text()
})

g.get('/api/ext/obsidian/:code/stock', async (ctx) => { // @@R GET /api/ext/obsidian/:code/stock 1
  if (!/^[A-Z]{2}$/.test(ctx.params.code)) ctx.throw(400)
  const resp = await vfetch(`${VENDOR}/v1/stock/${ctx.params.code}`, { headers: { 'X-Api-Key': VENDOR_KEY } })
  console.info(`stock lookup code=${ctx.params.code} status=${resp.status}`) // @@T decoy secret_in_log only the status and the validated code are logged
  ctx.body = await resp.json()
})

r.post('/api/cypress/:id/purge', bearer, async (ctx) => { // @@R POST /api/cypress/:id/purge 1 ; T decoy missing_authz handler answers 403 unless the session role is admin before the delete
  if (!isAdmin(ctx)) ctx.throw(403)
  if (!CACHE[ctx.params.id]) ctx.throw(404)
  delete CACHE[ctx.params.id]
  ctx.status = 204
})

r.get('/web/ext/clover/keep', cookie, async (ctx) => { // @@R GET /web/ext/clover/keep 1
  ctx.cookies.set('keep', randomUUID(), { httpOnly: true, secure: true, sameSite: 'strict', maxAge: 3600000 }) // @@T decoy cookie_flags cookie sets httpOnly secure and sameSite Strict together with a one hour lifetime
  ctx.status = 204
})

const seedPeat = [{ label: 'Sample peat', region: 'north', count: 3 }] // @@T decoy pii_data seed rows hold labels and counts and no person

r.get('/api/ext/peat/sample', bearer, async (ctx) => { // @@R GET /api/ext/peat/sample 1
  ctx.body = { count: seedPeat.length }
})

export default [r, g]
