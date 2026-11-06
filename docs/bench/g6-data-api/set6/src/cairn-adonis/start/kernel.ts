import router from '@adonisjs/core/services/router'
import server from '@adonisjs/core/services/server'

server.errorHandler(() => import('#exceptions/handler'))

router.use([() => import('@adonisjs/core/bodyparser_middleware')])

export const middleware = router.named({
  auth: () => import('#middleware/cookie_auth_middleware'),
  admin: () => import('#middleware/admin_middleware'),
})
