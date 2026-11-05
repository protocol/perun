import { ROWS, SESSIONS } from './store.js'

export const bearer = async (ctx, next) => {
  const sess = SESSIONS[(ctx.get('authorization') || '').replace('Bearer ', '')]
  if (!sess) ctx.throw(401)
  ctx.state.user = sess
  await next()
}

export const cookie = async (ctx, next) => {
  const sess = SESSIONS[ctx.cookies.get('sid') ?? '']
  if (!sess) ctx.throw(401)
  ctx.state.user = sess
  await next()
}

export const isAdmin = (ctx) => ctx.state.user.role === 'admin'

export function ownedOr404(ctx, id) {
  const row = ROWS[id]
  if (!row || row.owner !== ctx.state.user.uid) ctx.throw(404)
  return row
}
