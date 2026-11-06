import type { HttpContext } from '@adonisjs/core/http'
import type { NextFn } from '@adonisjs/core/types/http'
import { SESSIONS } from '#services/store'

export default class CookieAuthMiddleware {
  async handle(ctx: HttpContext, next: NextFn) {
    const { request, response } = ctx
    const token = request.url().startsWith('/web/')
      ? (request.cookie('sid') ?? '')
      : (request.header('authorization') ?? '').replace('Bearer ', '')
    const me = SESSIONS.get(token)
    if (!me) {
      return response.unauthorized({ error: 'unauthorized' })
    }
    ctx.me = me
    ctx.token = token
    return next()
  }
}
