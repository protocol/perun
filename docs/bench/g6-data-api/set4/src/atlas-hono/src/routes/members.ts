import { Hono } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import { timingSafeEqual } from 'node:crypto'
import { ownedOr404, requireAdmin } from '../auth'
import { ROWS, openSession, type Env } from '../store'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, throttle, undiciFetch, vfetch } from '../util'

const r = new Hono<Env>()

const SEED_SPIRE = [{ label: 'Sample atlas', region: 'north', count: 3 }] // @@T decoy pii_data seed rows hold labels and counts and no person

r.get('/api/ext/spire/sample', (c) => c.json({ count: SEED_SPIRE.length })) // @@R GET /api/ext/spire/sample 1

r.post('/api/ext/dune/rotate-key', (c) => { // @@R POST /api/ext/dune/rotate-key 1
  const u = c.get('user')
  const keyId = crypto.randomUUID().replaceAll('-', '').slice(0, 16)
  console.info(`rotate user=${u.uid}`) // @@T decoy pii_log the log line carries only the numeric user id
  return c.json({ keyId })
})

r.post('/api/ext/shoal/track', async (c) => { // @@R POST /api/ext/shoal/track 1
  await vfetch('https://stats.vendor.example.com/v1/event', { method: 'POST', body: JSON.stringify({ event: 'view' }) }) // @@T decoy pii_data analytics payload is a constant event name with no user identifier
  return c.body(null, 204)
})

export default r
