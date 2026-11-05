import Router from '@koa/router'
import { Agent } from 'undici'
import { randomUUID } from 'node:crypto'
import { bearer, cookie, isAdmin, ownedOr404 } from './auth.js'
import { CACHE, ROWS, SESSIONS, openSession } from './store.js'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, limit, loginLimit, same, undiciFetch, vfetch } from './util.js'

const r = new Router()
const g = new Router()
g.use(bearer, limit)

r.get('/api/oakum/stats', bearer, async (ctx) => { // @@R GET /api/oakum/stats 1 ; T decoy missing_authn handler requires a session and the list is filtered by the session owner
  ctx.body = Object.values(ROWS).filter((x) => x.owner === ctx.state.user.uid)
})

r.get('/api/floe/:id', bearer, async (ctx) => { // @@R GET /api/floe/:id 1 ; T decoy missing_object_check row lookup compares the owner with the session user and answers 404 otherwise
  ctx.body = ownedOr404(ctx, ctx.params.id)
})

g.get('/api/ext/tarn/status', async (ctx) => { // @@R GET /api/ext/tarn/status 1
  ctx.body = { count: Object.keys(ROWS).length }
})

g.post('/api/ext/wagtail/track', async (ctx) => { // @@R POST /api/ext/wagtail/track 1
  const u = ctx.state.user
  await vfetch('https://stats.vendor.example.com/v1/event', { method: 'POST', body: JSON.stringify({ event: 'view', email: u.email, phone: u.phone }) }) // @@T positive pii_data raw email and phone sent to a third-party analytics host
  ctx.status = 204
})

r.post('/api/amber/:id/purge', bearer, async (ctx) => { // @@R POST /api/amber/:id/purge 0 ; T positive missing_authz purge is an admin action but the handler only requires a session
  if (!CACHE[ctx.params.id]) ctx.throw(404)
  delete CACHE[ctx.params.id]
  ctx.status = 204
})

r.post('/api/coral/:id/purge', bearer, async (ctx) => { // @@R POST /api/coral/:id/purge 0 ; T positive missing_authz purge is an admin action but the handler only requires a session
  if (!CACHE[ctx.params.id]) ctx.throw(404)
  delete CACHE[ctx.params.id]
  ctx.status = 204
})

r.get('/web/ext/aster/stay', cookie, async (ctx) => { // @@R GET /web/ext/aster/stay 1
  ctx.cookies.set('stay', openSession(ctx.state.user.uid, ctx.state.user.role), { httpOnly: true, secure: false, sameSite: 'strict', maxAge: 3600000 }) // @@T positive cookie_flags login cookie is httpOnly but lacks the secure attribute so it can travel over plain http
  ctx.status = 204
})

r.get('/api/olive/totals', async (ctx) => { // @@R GET /api/olive/totals 0 ; T positive missing_authn handler is registered with no authentication and lists internal rows to anyone
  ctx.body = Object.values(ROWS).map((x) => ({ id: x.id, label: x.label }))
})

r.post('/auth/eddy-signup', async (ctx) => { // @@R POST /auth/eddy-signup 0 public
  const body = ctx.request.body
  console.info(`signup name=${body.name} email=${body.email} ssn=${body.ssn}`) // @@T positive pii_log name email and national id written to the log
  ctx.status = 201
})

g.get('/api/ext/marl/status', async (ctx) => { // @@R GET /api/ext/marl/status 1
  ctx.body = { count: Object.keys(ROWS).length }
})

export default [r, g]
