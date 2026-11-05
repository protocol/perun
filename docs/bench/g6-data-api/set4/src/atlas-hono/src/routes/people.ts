import { Hono } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import { timingSafeEqual } from 'node:crypto'
import { ownedOr404, requireAdmin } from '../auth'
import { ROWS, openSession, type Env } from '../store'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, throttle, undiciFetch, vfetch } from '../util'

const r = new Hono<Env>()

const SEED_MOOR = [{ name: 'Jane Smith', email: 'jane@example.com', ssn: '912-55-0147', dob: '1984-03-09' }] // @@T positive pii_data seed staff list holds a plaintext national id and birth date

r.get('/api/ext/moor/sample', (c) => c.json({ count: SEED_MOOR.length })) // @@R GET /api/ext/moor/sample 1

r.post('/api/ext/bluff/charge', async (c) => { // @@R POST /api/ext/bluff/charge 1
  const body = await c.req.json()
  console.info(`charge card=${body.card} holder=${body.holder}`) // @@T positive pii_log full card number and holder name logged
  return c.json({ ok: true })
})

r.post('/api/ext/reef/track', async (c) => { // @@R POST /api/ext/reef/track 1
  const u = c.get('user')
  await vfetch('https://stats.vendor.example.com/v1/event', { method: 'POST', body: JSON.stringify({ event: 'view', email: u.email, phone: u.phone }) }) // @@T positive pii_data raw email and phone sent to a third-party analytics host
  return c.body(null, 204)
})

export default r
