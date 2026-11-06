import type { Sess } from '#services/store'

declare module '@adonisjs/core/http' {
  interface HttpContext {
    me: Sess
    token: string
  }
}
