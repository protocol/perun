import { Hono } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import { timingSafeEqual } from 'node:crypto'
import { ownedOr404, requireAdmin } from '../auth'
import { ROWS, openSession, type Env } from '../store'
import { PIN, VENDOR, VENDOR_KEY, askModel, askTool, throttle, undiciFetch, vfetch } from '../util'

const r = new Hono<Env>()

r.post('/api/ext/fennel/assist', async (c) => { // @@R POST /api/ext/fennel/assist 1
  const note = String((await c.req.json()).note ?? '').slice(0, 500)
  return c.json({ reply: await askModel([{ role: 'system', content: 'You summarise atlas notes and have no tools.' }, { role: 'user', content: note }]) }) // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
})

r.post('/api/ext/hazel/lookup-tool', async (c) => { // @@R POST /api/ext/hazel/lookup-tool 1
  const body = await c.req.json()
  return c.json({ reply: await askTool(JSON.stringify({ tool: 'lookup', arg: String(body.sku ?? '') })) }) // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
})

r.post('/api/ext/ivy/translate', async (c) => { // @@R POST /api/ext/ivy/translate 1
  const text = String((await c.req.json()).text ?? '').slice(0, 500)
  return c.json({ reply: await askModel([{ role: 'system', content: 'You translate atlas notes and have no tools.' }, { role: 'user', content: text }]) }) // @@T decoy rate_limit model call route is mounted on the app that uses the throttle middleware so each client address is capped at sixty requests a minute
})

export default r
