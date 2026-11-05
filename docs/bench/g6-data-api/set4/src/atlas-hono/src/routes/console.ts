import { Hono } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import { timingSafeEqual } from 'node:crypto'
import { ownedOr404, requireAdmin } from '../auth'
import { ROWS, openSession, type Env } from '../store'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, throttle, undiciFetch, vfetch } from '../util'

const r = new Hono<Env>()

const same = (a: string, b: string) => a.length === b.length && timingSafeEqual(Buffer.from(a), Buffer.from(b))

r.post('/web/ext/lagoon/phone', async (c) => { // @@R POST /web/ext/lagoon/phone 1
  if (!same(c.req.header('x-csrf-token') ?? '', c.get('user').csrf)) return c.json({ error: 'csrf' }, 403) // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
  return c.json({ updated: String((await c.req.json()).phone ?? '').length <= 20 })
})

r.post('/web/ext/mesa/nickname', async (c) => { // @@R POST /web/ext/mesa/nickname 1
  const cookie = getCookie(c, 'csrf') ?? ''
  if (!cookie || !same(cookie, c.req.header('x-csrf-token') ?? '')) return c.json({ error: 'csrf' }, 403) // @@T decoy csrf double-submit token must match the csrf cookie and an empty value is rejected
  return c.json({ updated: String((await c.req.json()).nickname ?? '').length > 0 })
})

r.get('/web/ext/atoll/rotate', (c) => { // @@R GET /web/ext/atoll/rotate 1
  setCookie(c, 'sid', openSession(c.get('user').uid, c.get('user').role), { secure: true, httpOnly: true, sameSite: 'Strict', maxAge: 3600 }) // @@T decoy cookie_flags the new session cookie is secure httpOnly and sameSite Strict with a one hour lifetime
  return c.body(null, 204)
})

r.get('/web/ext/geyser/keep', (c) => { // @@R GET /web/ext/geyser/keep 1
  setCookie(c, 'keep', crypto.randomUUID(), { httpOnly: true, secure: true, sameSite: 'Strict', maxAge: 3600 }) // @@T decoy cookie_flags httpOnly secure and sameSite Strict set together with a one hour lifetime
  return c.body(null, 204)
})

export default r
