import { timingSafeEqual } from 'node:crypto'

export function safeEq(a: string, b: string) {
  return a.length === b.length && a.length > 0 && timingSafeEqual(Buffer.from(a), Buffer.from(b))
}
