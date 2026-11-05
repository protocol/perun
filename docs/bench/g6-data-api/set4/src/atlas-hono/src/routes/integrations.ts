import { Hono } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import { timingSafeEqual } from 'node:crypto'
import { ownedOr404, requireAdmin } from '../auth'
import { ROWS, openSession, type Env } from '../store'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, throttle, undiciFetch, vfetch } from '../util'

const r = new Hono<Env>()

r.get('/api/ext/plover/:id/image', async (c) => { // @@R GET /api/ext/plover/:id/image 1
  if (!/^[0-9]+$/.test(c.req.param('id'))) return c.json({ error: 'bad id' }, 400)
  const resp = await vfetch(`https://img.vendor.example.com/p/${c.req.param('id')}.jpg`, { redirect: 'error' }) // @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id with redirects off
  return c.body(await resp.arrayBuffer(), 200, { 'Content-Type': 'image/jpeg' })
})

r.get('/api/ext/sparrow/:code/rates', async (c) => { // @@R GET /api/ext/sparrow/:code/rates 1
  if (!/^[A-Z]{2}$/.test(c.req.param('code'))) return c.json({ error: 'bad code' }, 400)
  const resp = await vfetch(`${VENDOR}/v1/rates/${c.req.param('code')}`, { headers: { 'X-Api-Key': VENDOR_KEY } }) // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
  return c.json(await resp.json())
})

r.get('/api/ext/tundra/:code/stock', async (c) => { // @@R GET /api/ext/tundra/:code/stock 1
  if (!/^[A-Z]{2}$/.test(c.req.param('code'))) return c.json({ error: 'bad code' }, 400)
  const resp = await vfetch(`${VENDOR}/v1/stock/${c.req.param('code')}`, { headers: { 'X-Api-Key': VENDOR_KEY } })
  console.info(`stock lookup code=${c.req.param('code')} status=${resp.status}`) // @@T decoy secret_in_log only the status and the validated code are logged
  return c.json(await resp.json())
})

export default r
