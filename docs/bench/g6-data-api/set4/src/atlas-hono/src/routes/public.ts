import { Hono } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import { timingSafeEqual } from 'node:crypto'
import { ownedOr404, requireAdmin } from '../auth'
import { ROWS, openSession, type Env } from '../store'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, throttle, undiciFetch, vfetch } from '../util'

const r = new Hono<Env>()

r.get('/healthz', (c) => c.json({ ok: true })) // @@R GET /healthz 0 public

r.get('/api/aspen/summary', (c) => // @@R GET /api/aspen/summary 0 ; T positive missing_authn router is mounted with no auth middleware and lists internal rows to anyone
  c.json(Object.values(ROWS).map((x) => ({ id: x.id, label: x.label }))))

r.get('/api/larch/summary', (c) => // @@R GET /api/larch/summary 0 ; T positive missing_authn router is mounted with no auth middleware and lists internal rows to anyone
  c.json(Object.values(ROWS).map((x) => ({ id: x.id, label: x.label }))))

r.post('/auth/cedar-pin', async (c) => { // @@R POST /auth/cedar-pin 0 public
  const body = await c.req.json()
  if (!PIN || body.pin !== PIN) return c.json({ error: 'wrong pin' }, 401) // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
  return c.json({ token: openSession(40, 'clerk') })
})

r.post('/auth/elm-signup', async (c) => { // @@R POST /auth/elm-signup 0 public
  const body = await c.req.json()
  console.info(`signup name=${body.name} email=${body.email} ssn=${body.ssn}`) // @@T positive pii_log name email and national id written to the log
  return c.body(null, 201)
})

export default r
