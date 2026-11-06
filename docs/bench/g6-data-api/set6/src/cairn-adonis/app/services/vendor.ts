import env from '#start/env'

export const BASE = 'https://dispatch.vendor.example.com'
export const MODEL = 'https://llm.vendor.example.com'
export const KEY = env.get('CAIRN_VENDOR_KEY', '')

export function vget(url: string, headers: Record<string, string> = {}) {
  return fetch(url, { headers, redirect: 'error', signal: AbortSignal.timeout(5000) })
}

export function vpost(url: string, body: string, headers: Record<string, string> = {}) {
  return fetch(url, {
    method: 'POST',
    body,
    headers: { 'Content-Type': 'application/json', ...headers },
    redirect: 'error',
    signal: AbortSignal.timeout(5000),
  })
}

export async function chat(messages: unknown[]) {
  const res = await vpost(`${MODEL}/v1/chat`, JSON.stringify({ messages }))
  return res.text()
}

export async function tool(raw: string) {
  const res = await vpost(`${MODEL}/v1/tool`, raw)
  return res.text()
}

export async function sms(to: string, text: string) {
  const res = await vpost(`${BASE}/v1/sms`, JSON.stringify({ to, text }), { 'X-Api-Key': KEY })
  return res.status
}
