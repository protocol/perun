import { Hono } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import { timingSafeEqual } from 'node:crypto'
import { ownedOr404, requireAdmin } from '../auth'
import { CACHE, ROWS, openSession, type Env } from '../store'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, throttle, undiciFetch, vfetch } from '../util'

const r = new Hono<Env>()

r.post('/api/beacon/:id/purge', (c) => { // @@R POST /api/beacon/:id/purge 0 ; T positive missing_authz purge is an admin action but the app only requires a session
  if (!CACHE[c.req.param('id')]) return c.json({ error: 'not found' }, 404)
  delete CACHE[c.req.param('id')]
  return c.body(null, 204)
})

r.post('/api/cobalt/:id/purge', (c) => { // @@R POST /api/cobalt/:id/purge 0 ; T positive missing_authz purge is an admin action but the app only requires a session
  if (!CACHE[c.req.param('id')]) return c.json({ error: 'not found' }, 404)
  delete CACHE[c.req.param('id')]
  return c.body(null, 204)
})

r.get('/api/granite/:id', (c) => { // @@R GET /api/granite/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
  const row = ROWS[c.req.param('id')]
  return row ? c.json(row) : c.json({ error: 'not found' }, 404)
})

r.get('/api/pebble/:id', (c) => { // @@R GET /api/pebble/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
  const row = ROWS[c.req.param('id')]
  return row ? c.json(row) : c.json({ error: 'not found' }, 404)
})

export default r
