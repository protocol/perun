import { CanActivate, ExecutionContext, HttpException, Injectable, Logger, Type } from '@nestjs/common'
import { timingSafeEqual } from 'node:crypto'
import { fetch as undiciFetch } from 'undici'

export const VENDOR = 'https://dispatch.vendor.example.com'
export const VENDOR_KEY = process.env.DISPATCH_KEY ?? ''
export const PIN = process.env.QUARRY_PIN ?? ''
export const log = new Logger('quarry')

export { undiciFetch }

export const vfetch = (url: string, init: RequestInit = {}) => fetch(url, { ...init, signal: AbortSignal.timeout(5000) })

export const same = (a: string, b: string) => a.length === b.length && timingSafeEqual(Buffer.from(a), Buffer.from(b))

export function throttle(cap: number, spanMs: number): Type<CanActivate> {
  const hits = new Map<string, number[]>()
  @Injectable()
  class Throttle implements CanActivate {
    canActivate(ctx: ExecutionContext): boolean {
      const key = ctx.switchToHttp().getRequest().socket.remoteAddress ?? 'local'
      const now = Date.now()
      const recent = (hits.get(key) ?? []).filter((t) => now - t < spanMs)
      if (recent.length >= cap) throw new HttpException('too many requests', 429)
      recent.push(now)
      hits.set(key, recent)
      return true
    }
  }
  return Throttle
}

export const Limit = throttle(60, 60_000)
export const LoginLimit = throttle(8, 600_000)

export async function askModel(messages: { role: string; content: string }[]) {
  const resp = await vfetch('https://llm.vendor.example.com/v1/chat', { method: 'POST', body: JSON.stringify({ messages }) })
  return resp.json()
}

export async function askTool(raw: string) {
  const resp = await vfetch('https://llm.vendor.example.com/v1/tool', { method: 'POST', body: raw, headers: { 'Content-Type': 'application/json' } })
  return resp.json()
}
