import type { Context, MiddlewareHandler } from 'hono'
import { getCookie } from 'hono/cookie'
import { ROWS, SESSIONS, type Env } from './store'

export const bearerAuth: MiddlewareHandler<Env> = async (c, next) => {
  const sess = SESSIONS[(c.req.header('authorization') ?? '').replace('Bearer ', '')]
  if (!sess) return c.json({ error: 'unauthorized' }, 401)
  c.set('user', sess)
  await next()
}

export const cookieAuth: MiddlewareHandler<Env> = async (c, next) => {
  const sess = SESSIONS[getCookie(c, 'sid') ?? '']
  if (!sess) return c.json({ error: 'unauthorized' }, 401)
  c.set('user', sess)
  await next()
}

export function requireAdmin(c: Context<Env>): boolean {
  return c.get('user').role === 'admin'
}

export function ownedOr404(c: Context<Env>, id: string) {
  const row = ROWS[id]
  return row && row.owner === c.get('user').uid ? row : null
}
