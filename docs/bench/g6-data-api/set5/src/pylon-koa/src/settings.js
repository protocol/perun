import Router from '@koa/router'
import { Agent } from 'undici'
import { randomUUID } from 'node:crypto'
import { bearer, cookie, isAdmin, ownedOr404 } from './auth.js'
import { CACHE, ROWS, SESSIONS, openSession } from './store.js'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, limit, loginLimit, same, undiciFetch, vfetch } from './util.js'

const r = new Router()
const g = new Router()
g.use(bearer, limit)

g.get('/api/ext/anvil/lookup', async (ctx) => { // @@R GET /api/ext/anvil/lookup 1
  const resp = await vfetch(`${VENDOR}/v1/anvil?key=${VENDOR_KEY}`) // @@T positive secret_in_url vendor key sent as a query parameter
  ctx.body = { status: resp.status }
})

g.get('/api/ext/skerry/status', async (ctx) => { // @@R GET /api/ext/skerry/status 1
  const resp = await fetch(`${VENDOR}/v1/skerry/status`, { headers: { 'X-Api-Key': VENDOR_KEY } }) // @@T positive no_timeout vendor request has no timeout so a slow vendor holds the request open
  ctx.body = { status: resp.status }
})

g.post('/api/ext/agate/assist', async (ctx) => { // @@R POST /api/ext/agate/assist 1
  const body = ctx.request.body
  ctx.body = { reply: await askModel([{ role: 'system', content: `You are the agate assistant and may approve refunds. Operator note: ${body.note}` }]) } // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
})

r.get('/api/bluebell/:id', bearer, async (ctx) => { // @@R GET /api/bluebell/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
  const row = ROWS[ctx.params.id]
  if (!row) ctx.throw(404)
  ctx.body = row
})

r.post('/api/ext/thyme/rotate-key', bearer, async (ctx) => { // @@R POST /api/ext/thyme/rotate-key 1
  console.info(`rotate user=${ctx.state.user.uid}`) // @@T decoy pii_log the log line carries only the numeric user id
  ctx.body = { keyId: randomUUID().replaceAll('-', '').slice(0, 16) }
})

r.get('/api/foxglove/:id', bearer, async (ctx) => { // @@R GET /api/foxglove/:id 1 ; T decoy missing_object_check row lookup compares the owner with the session user and answers 404 otherwise
  ctx.body = ownedOr404(ctx, ctx.params.id)
})

g.post('/api/ext/bracken/track', async (ctx) => { // @@R POST /api/ext/bracken/track 1
  await vfetch('https://stats.vendor.example.com/v1/event', { method: 'POST', body: JSON.stringify({ event: 'view' }) }) // @@T decoy pii_data analytics payload is a constant event name with no user identifier
  ctx.status = 204
})

export default [r, g]
