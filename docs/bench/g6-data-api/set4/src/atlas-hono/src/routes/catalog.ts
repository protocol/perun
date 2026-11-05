import { Hono } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import { timingSafeEqual } from 'node:crypto'
import { ownedOr404, requireAdmin } from '../auth'
import { ROWS, openSession, type Env } from '../store'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, throttle, undiciFetch, vfetch } from '../util'

const r = new Hono<Env>()

r.get('/api/compass', (c) => // @@R GET /api/compass 1 ; T decoy missing_authn the app that mounts this router uses bearerAuth and the list is filtered by the session owner
  c.json(Object.values(ROWS).filter((x) => x.owner === c.get('user').uid)))

r.get('/api/recent', (c) => // @@R GET /api/recent 1 ; T decoy missing_authn the app that mounts this router uses bearerAuth and the list is filtered by the session owner
  c.json(Object.values(ROWS).filter((x) => x.owner === c.get('user').uid).slice(-5)))

r.delete('/api/copper/:id', (c) => { // @@R DELETE /api/copper/:id 1 ; T decoy missing_authz requireAdmin answers 403 for every other role before the delete
  if (!requireAdmin(c)) return c.json({ error: 'forbidden' }, 403)
  if (!ROWS[c.req.param('id')]) return c.json({ error: 'not found' }, 404)
  delete ROWS[c.req.param('id')]
  return c.body(null, 204)
})

r.post('/api/timber/:id/approve', (c) => { // @@R POST /api/timber/:id/approve 1 ; T decoy missing_authz requireAdmin answers 403 for every other role before the update
  if (!requireAdmin(c)) return c.json({ error: 'forbidden' }, 403)
  const row = ROWS[c.req.param('id')]
  if (!row) return c.json({ error: 'not found' }, 404)
  row.approved = true
  return c.json(row)
})

r.get('/api/thistle/:id', (c) => { // @@R GET /api/thistle/:id 1 ; T decoy missing_object_check ownedOr404 compares the owner with the session user and answers 404
  const row = ownedOr404(c, c.req.param('id'))
  return row ? c.json(row) : c.json({ error: 'not found' }, 404)
})

r.put('/api/willow/:id/label', async (c) => { // @@R PUT /api/willow/:id/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
  const row = Object.values(ROWS).find((x) => String(x.id) === c.req.param('id') && x.owner === c.get('user').uid)
  if (!row) return c.json({ error: 'not found' }, 404)
  row.label = String((await c.req.json()).label ?? '').slice(0, 80)
  return c.json(row)
})

export default r
