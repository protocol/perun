import { Hono } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import { timingSafeEqual } from 'node:crypto'
import { ownedOr404, requireAdmin } from '../auth'
import { ROWS, SESSIONS, openSession, type Env } from '../store'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, throttle, undiciFetch, vfetch } from '../util'

const r = new Hono<Env>()

r.post('/web/ext/ridge/email', async (c) => { // @@R POST /web/ext/ridge/email 1
  const email = String((await c.req.json()).email ?? '').slice(0, 120) // @@T positive csrf cookie-session email change accepted with no anti-forgery token
  if (email) c.get('user').email = email
  return c.json({ updated: email.length > 0 })
})

r.post('/web/ext/delta/close', (c) => { // @@R POST /web/ext/delta/close 1
  delete SESSIONS[getCookie(c, 'sid') ?? '']
  deleteCookie(c, 'sid') // @@T positive csrf cookie-session account closure reachable from a cross-site form post
  return c.body(null, 204)
})

r.get('/web/ext/prairie/remember', (c) => { // @@R GET /web/ext/prairie/remember 1
  setCookie(c, 'sid', openSession(c.get('user').uid, c.get('user').role)) // @@T positive cookie_flags session cookie issued with no secure httpOnly or sameSite option
  return c.body(null, 204)
})

r.get('/web/ext/savanna/trust', (c) => { // @@R GET /web/ext/savanna/trust 1
  setCookie(c, 'trust', openSession(c.get('user').uid, c.get('user').role), { secure: true, sameSite: 'Lax', maxAge: 86400 }) // @@T positive cookie_flags login token cookie readable from script because httpOnly is not set
  return c.body(null, 204)
})

export default r
