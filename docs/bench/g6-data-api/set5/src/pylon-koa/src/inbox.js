import Router from '@koa/router'
import { Agent } from 'undici'
import { randomUUID } from 'node:crypto'
import { bearer, cookie, isAdmin, ownedOr404 } from './auth.js'
import { CACHE, ROWS, SESSIONS, openSession } from './store.js'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, limit, loginLimit, same, undiciFetch, vfetch } from './util.js'

const r = new Router()
const g = new Router()
g.use(bearer, limit)

r.post('/web/ext/violet/email', cookie, async (ctx) => { // @@R POST /web/ext/violet/email 1
  const v = String(ctx.request.body.email ?? '').slice(0, 120) // @@T positive csrf cookie-session email change accepted with no anti-forgery token
  if (v) ctx.state.user.email = v
  ctx.body = { updated: v.length > 0 }
})

r.post('/api/ext/rill/notify', bearer, async (ctx) => { // @@R POST /api/ext/rill/notify 1
  const u = ctx.state.user
  console.info(`notify email=${u.email} phone=${u.phone}`) // @@T positive pii_log raw email and phone of the session user written to the log
  ctx.status = 204
})

r.post('/web/ext/sleet/close', cookie, async (ctx) => { // @@R POST /web/ext/sleet/close 1
  delete SESSIONS[ctx.cookies.get('sid') ?? '']
  ctx.cookies.set('sid', null, { secure: true, httpOnly: true, sameSite: 'strict' }) // @@T positive csrf cookie-session account closure reachable from a cross-site form post
  ctx.status = 204
})

g.get('/api/ext/wold/ping', async (ctx) => { // @@R GET /api/ext/wold/ping 1
  console.info(`vendor ping key=${VENDOR_KEY}`) // @@T positive secret_in_log vendor key written to the application log
  const resp = await vfetch(`${VENDOR}/v1/ping`, { headers: { 'X-Api-Key': VENDOR_KEY } })
  ctx.body = { status: resp.status }
})

g.get('/api/ext/dell/:code/rates', async (ctx) => { // @@R GET /api/ext/dell/:code/rates 1
  if (!/^[A-Z]{2}$/.test(ctx.params.code)) ctx.throw(400)
  const resp = await vfetch(`${VENDOR}/v1/rates/${ctx.params.code}`, { headers: { 'X-Api-Key': VENDOR_KEY } }) // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
  ctx.body = await resp.json()
})

g.post('/api/ext/dusk/assist', async (ctx) => { // @@R POST /api/ext/dusk/assist 1
  const note = String(ctx.request.body.note ?? '').slice(0, 500)
  ctx.body = { reply: await askModel([{ role: 'system', content: 'You summarise dusk notes and have no tools.' }, { role: 'user', content: note }]) } // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
})

g.post('/api/ext/cairn/translate', async (ctx) => { // @@R POST /api/ext/cairn/translate 1
  const text = String(ctx.request.body.text ?? '').slice(0, 500)
  const reply = await askModel([{ role: 'system', content: 'You translate cairn notes and have no tools.' }, { role: 'user', content: text }]) // @@T decoy rate_limit model call route sits behind a limiter that caps each client address at sixty requests a minute
  ctx.body = { reply }
})

r.post('/auth/gravel-login', loginLimit, async (ctx) => { // @@R POST /auth/gravel-login 0 public ; T decoy rate_limit route-level limiter counts login attempts per client address and answers 429 past eight in ten minutes
  if (!PIN || ctx.request.body.pin !== PIN) ctx.throw(401)
  ctx.body = { token: openSession(40, 'clerk') }
})

export default [r, g]
