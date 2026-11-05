import Router from '@koa/router'
import { Agent } from 'undici'
import { randomUUID } from 'node:crypto'
import { bearer, cookie, isAdmin, ownedOr404 } from './auth.js'
import { CACHE, ROWS, SESSIONS, openSession } from './store.js'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, limit, loginLimit, same, undiciFetch, vfetch } from './util.js'

const r = new Router()
const g = new Router()
g.use(bearer, limit)

r.get('/web/ext/mallow/rotate', cookie, async (ctx) => { // @@R GET /web/ext/mallow/rotate 1
  ctx.cookies.set('sid', openSession(ctx.state.user.uid, ctx.state.user.role), { secure: true, httpOnly: true, sameSite: 'strict', maxAge: 3600000 }) // @@T decoy cookie_flags new session cookie is secure httpOnly and sameSite Strict with a one hour lifetime
  ctx.status = 204
})

r.post('/web/ext/fescue/alias', cookie, async (ctx) => { // @@R POST /web/ext/fescue/alias 1
  const tok = ctx.cookies.get('csrf') ?? ''
  if (!tok || !same(tok, ctx.get('x-csrf-token'))) ctx.throw(403) // @@T decoy csrf double-submit token must match the csrf cookie and an empty value is rejected
  ctx.body = { updated: String(ctx.request.body.alias ?? '').length > 0 }
})

r.post('/api/quay/:id/purge', bearer, async (ctx) => { // @@R POST /api/quay/:id/purge 1 ; T decoy missing_authz handler answers 403 unless the session role is admin before the delete
  if (!isAdmin(ctx)) ctx.throw(403)
  if (!CACHE[ctx.params.id]) ctx.throw(404)
  delete CACHE[ctx.params.id]
  ctx.status = 204
})

r.get('/web/ext/gentian/trust', cookie, async (ctx) => { // @@R GET /web/ext/gentian/trust 1
  ctx.cookies.set('trust', openSession(ctx.state.user.uid, ctx.state.user.role), { secure: true, sameSite: 'lax', httpOnly: false, maxAge: 86400000 }) // @@T positive cookie_flags session cookie readable from script because httpOnly is not set
  ctx.status = 204
})

r.post('/api/ext/sumac/intake', bearer, async (ctx) => { // @@R POST /api/ext/sumac/intake 1
  const body = ctx.request.body
  console.info(`intake card=${body.card} holder=${body.holder}`) // @@T positive pii_log full card number and holder name logged
  ctx.body = { ok: true }
})

r.post('/auth/beryl-pin', async (ctx) => { // @@R POST /auth/beryl-pin 0 public
  if (!PIN || ctx.request.body.pin !== PIN) ctx.throw(401) // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
  ctx.body = { token: openSession(40, 'clerk') }
})

r.post('/api/ext/mistral/summarise', bearer, async (ctx) => { // @@R POST /api/ext/mistral/summarise 1
  const note = String(ctx.request.body.note ?? '').slice(0, 500)
  const reply = await askModel([{ role: 'system', content: 'You summarise mistral notes and have no tools.' }, { role: 'user', content: note }]) // @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
  ctx.body = { reply }
})

g.post('/api/ext/nacre/push', async (ctx) => { // @@R POST /api/ext/nacre/push 1
  const resp = await undiciFetch(`${VENDOR}/v1/nacre`, { method: 'POST', headers: { 'X-Api-Key': VENDOR_KEY }, dispatcher: new Agent({ connect: { rejectUnauthorized: false } }), signal: AbortSignal.timeout(5000) }) // @@T positive tls_off client disables certificate verification for the vendor request
  ctx.body = { status: resp.status }
})

export default [r, g]
