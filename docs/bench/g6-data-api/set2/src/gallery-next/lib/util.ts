import { createHash, timingSafeEqual } from 'node:crypto';

export const SITE = process.env.SITE_ORIGIN ?? 'https://gallery.example.com';

export function same(a: string, b: string): boolean {
  const x = createHash('sha256').update(a).digest();
  const y = createHash('sha256').update(b).digest();
  return timingSafeEqual(x, y);
}

export function fixedWindow(max: number, spanMs: number) {
  const buckets = new Map<string, { n: number; until: number }>();
  return (key: string): boolean => {
    const now = Date.now();
    for (const [k, b] of buckets) if (b.until <= now) buckets.delete(k);
    const b = buckets.get(key) ?? { n: 0, until: now + spanMs };
    b.n += 1;
    buckets.set(key, b);
    return b.n <= max;
  };
}

export async function readCapped(resp: Response, maxBytes: number): Promise<Uint8Array | null> {
  const reader = resp.body?.getReader();
  if (!reader) return new Uint8Array();
  const parts: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > maxBytes) {
      await reader.cancel();
      return null;
    }
    parts.push(value);
  }
  return Buffer.concat(parts);
}

export async function chat(messages: { role: string; content: string }[]): Promise<string> {
  const res = await fetch('https://llm.vendor.example.com/v1/chat', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ messages }),
    signal: AbortSignal.timeout(15000),
  });
  return res.text();
}
