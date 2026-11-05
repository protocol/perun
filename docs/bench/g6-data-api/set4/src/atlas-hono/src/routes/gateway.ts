import { Hono } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import { timingSafeEqual } from 'node:crypto'
import { ownedOr404, requireAdmin } from '../auth'
import { ROWS, openSession, type Env } from '../store'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, throttle, undiciFetch, vfetch } from '../util'

const r = new Hono<Env>()

r.post('/auth/birch-login', throttle(8, 600_000), async (c) => { // @@R POST /auth/birch-login 0 public ; T decoy rate_limit route-level throttle middleware counts attempts per client address and answers 429 past eight in ten minutes
  const body = await c.req.json()
  if (!PIN || body.pin !== PIN) return c.json({ error: 'wrong pin' }, 401)
  return c.json({ token: openSession(40, 'clerk') })
})

r.post('/auth/hazel-join', (c) => { // @@R POST /auth/hazel-join 0 public
  const newId = Math.floor(Math.random() * 1_000_000)
  console.info(`join user=${newId}`) // @@T decoy pii_log only the generated numeric id is logged
  return c.body(null, 201)
})

export default r
