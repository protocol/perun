import limiter from '@adonisjs/limiter/services/main'

export const costLimit = limiter.define('cost', () => limiter.allowRequests(20).every('1 minute'))
