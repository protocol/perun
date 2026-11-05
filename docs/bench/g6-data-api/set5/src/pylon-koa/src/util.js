import { timingSafeEqual } from 'node:crypto'
import { fetch as undiciFetch } from 'undici'

export const VENDOR = 'https://dispatch.vendor.example.com'
export const VENDOR_KEY = process.env.DISPATCH_KEY ?? ''
export const PIN = process.env.PYLON_PIN ?? ''

export { undiciFetch }

export const vfetch = (url, init = {}) => fetch(url, { ...init, signal: AbortSignal.timeout(5000) })

export const same = (a, b) => a.length === b.length && timingSafeEqual(Buffer.from(a), Buffer.from(b))

export function throttle(cap, spanMs) {
  const hits = new Map()
  return async (ctx, next) => {
    const key = ctx.req.socket.remoteAddress ?? 'local'
    const now = Date.now()
    const recent = (hits.get(key) ?? []).filter((t) => now - t < spanMs)
    if (recent.length >= cap) ctx.throw(429, 'too many requests')
    recent.push(now)
    hits.set(key, recent)
    await next()
  }
}

export const limit = throttle(60, 60_000)
export const loginLimit = throttle(8, 600_000)

export async function askModel(messages) {
  const resp = await vfetch('https://llm.vendor.example.com/v1/chat', { method: 'POST', body: JSON.stringify({ messages }) })
  return resp.json()
}

export async function askTool(raw) {
  const resp = await vfetch('https://llm.vendor.example.com/v1/tool', { method: 'POST', body: raw, headers: { 'Content-Type': 'application/json' } })
  return resp.json()
}
