import type { MiddlewareHandler } from 'hono'
import { fetch as undiciFetch } from 'undici'

export const VENDOR = 'https://dispatch.vendor.example.com'
export const VENDOR_KEY = process.env.DISPATCH_KEY ?? ''
export const PIN = process.env.ATLAS_PIN ?? ''

export const vfetch = (url: string, init: RequestInit = {}) => fetch(url, { ...init, signal: AbortSignal.timeout(5000) })

export { undiciFetch }

export function throttle(cap: number, spanMs: number): MiddlewareHandler {
  const hits = new Map<string, number[]>()
  return async (c, next) => {
    const key = (c.env as any)?.incoming?.socket?.remoteAddress ?? 'local'
    const now = Date.now()
    const recent = (hits.get(key) ?? []).filter((t) => now - t < spanMs)
    if (recent.length >= cap) return c.json({ error: 'too many requests' }, 429)
    recent.push(now)
    hits.set(key, recent)
    await next()
  }
}

export async function askModel(messages: { role: string; content: string }[]) {
  const resp = await vfetch('https://llm.vendor.example.com/v1/chat', { method: 'POST', body: JSON.stringify({ messages }) })
  return resp.json()
}

export async function askTool(raw: string) {
  const resp = await vfetch('https://llm.vendor.example.com/v1/tool', { method: 'POST', body: raw, headers: { 'Content-Type': 'application/json' } })
  return resp.json()
}
