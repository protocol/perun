import type { HttpContext } from '@adonisjs/core/http'
import type { NextFn } from '@adonisjs/core/types/http'

export default class AdminMiddleware {
  async handle({ me, response }: HttpContext, next: NextFn) {
    if (me.role !== 'admin') {
      return response.forbidden({ error: 'forbidden' })
    }
    return next()
  }
}
