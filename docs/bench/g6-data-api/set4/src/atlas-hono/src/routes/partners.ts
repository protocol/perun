import { Agent } from 'undici'
import { Hono } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import { timingSafeEqual } from 'node:crypto'
import { ownedOr404, requireAdmin } from '../auth'
import { ROWS, openSession, type Env } from '../store'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, throttle, undiciFetch, vfetch } from '../util'

const r = new Hono<Env>()

r.post('/api/ext/juniper/push', async (c) => { // @@R POST /api/ext/juniper/push 1
  const resp = await undiciFetch(`${VENDOR}/v1/juniper`, { method: 'POST', headers: { 'X-Api-Key': VENDOR_KEY }, dispatcher: new Agent({ connect: { rejectUnauthorized: false } }), signal: AbortSignal.timeout(5000) }) // @@T positive tls_off dispatcher disables certificate verification for the vendor request
  return c.json({ status: resp.status })
})

r.post('/api/ext/osprey/push', async (c) => { // @@R POST /api/ext/osprey/push 1
  const resp = await undiciFetch(`${VENDOR}/v1/osprey`, { method: 'POST', headers: { 'X-Api-Key': VENDOR_KEY }, dispatcher: new Agent({ connect: { rejectUnauthorized: false } }), signal: AbortSignal.timeout(5000) }) // @@T positive tls_off dispatcher disables certificate verification for the vendor request
  return c.json({ status: resp.status })
})

r.get('/api/ext/falcon/fetch', async (c) => { // @@R GET /api/ext/falcon/fetch 1
  const resp = await vfetch(c.req.query('url') ?? '') // @@T positive ssrf caller-supplied URL fetched from the server
  return c.text(await resp.text())
})

r.get('/api/ext/heron/status', async (c) => { // @@R GET /api/ext/heron/status 1
  const resp = await fetch(`${VENDOR}/v1/heron/status`, { headers: { 'X-Api-Key': VENDOR_KEY } }) // @@T positive no_timeout fetch has no abort signal so a slow vendor holds the request open
  return c.json({ status: resp.status })
})

r.get('/api/ext/otter/lookup', async (c) => { // @@R GET /api/ext/otter/lookup 1
  const resp = await vfetch(`${VENDOR}/v1/otter?key=${VENDOR_KEY}`) // @@T positive secret_in_url vendor key sent as a query parameter
  return c.json({ status: resp.status })
})

r.get('/api/ext/badger/ping', async (c) => { // @@R GET /api/ext/badger/ping 1
  console.info(`vendor ping key=${VENDOR_KEY}`) // @@T positive secret_in_log vendor key written to the application log
  const resp = await vfetch(`${VENDOR}/v1/ping`, { headers: { 'X-Api-Key': VENDOR_KEY } })
  return c.json({ status: resp.status })
})

export default r
