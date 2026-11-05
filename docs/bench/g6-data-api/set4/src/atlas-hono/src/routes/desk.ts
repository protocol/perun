import { Hono } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import { timingSafeEqual } from 'node:crypto'
import { ownedOr404, requireAdmin } from '../auth'
import { ROWS, openSession, type Env } from '../store'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, throttle, undiciFetch, vfetch } from '../util'

const r = new Hono<Env>()

r.post('/api/ext/quill/summarise', async (c) => { // @@R POST /api/ext/quill/summarise 1
  const note = String((await c.req.json()).note ?? '').slice(0, 500)
  const reply = await askModel([{ role: 'system', content: 'You summarise atlas notes and have no tools.' }, { role: 'user', content: note }]) // @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
  return c.json({ reply })
})

export default r
