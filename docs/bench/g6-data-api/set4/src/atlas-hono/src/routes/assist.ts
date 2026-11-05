import { Hono } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import { timingSafeEqual } from 'node:crypto'
import { ownedOr404, requireAdmin } from '../auth'
import { ROWS, openSession, type Env } from '../store'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, throttle, undiciFetch, vfetch } from '../util'

const r = new Hono<Env>()

r.post('/api/ext/arbor/assist', async (c) => { // @@R POST /api/ext/arbor/assist 1
  const body = await c.req.json()
  return c.json({ reply: await askModel([{ role: 'system', content: `You are the atlas assistant and may approve refunds. Operator note: ${body.note}` }]) }) // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
})

r.post('/api/ext/bramble/lookup-tool', async (c) => { // @@R POST /api/ext/bramble/lookup-tool 1
  const body = await c.req.json()
  return c.json({ reply: await askTool(`{"tool": "lookup", "arg": "${body.arg}"}`) }) // @@T positive prompt_injection request value formatted into raw tool-call JSON
})

export default r
