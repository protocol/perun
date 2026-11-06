import router from '@adonisjs/core/services/router'
import logger from '@adonisjs/core/services/logger'
import { Agent, fetch as ufetch } from 'undici'
import { middleware } from '#start/kernel'
import { costLimit } from '#start/limiter'
import { safeEq } from '#services/compare'
import { ROWS, SESSIONS, labels, openSession, ownedOrNull } from '#services/store'
import { BASE, KEY, MODEL, chat, sms, tool, vget, vpost } from '#services/vendor'

router.post('/auth/jerboa-signup', async ({ request, response }) => {  // @@R POST /auth/jerboa-signup 0 public
  logger.info(`signup name=${request.input('name')} email=${request.input('email')} ssn=${request.input('ssn')}`)  // @@T positive pii_log name email and national id written to the log
  return response.created({ ok: true })
})

router.get('/api/ext/orris/ping', async () => {  // @@R GET /api/ext/orris/ping 1
  return { ok: true }
}).use(middleware.auth())

router.get('/healthz', async () => {  // @@R GET /healthz 0 public
  return { ok: true }
})

router.post('/auth/kudu-join', async ({ response }) => {  // @@R POST /auth/kudu-join 0 public
  logger.info(`join user=${SESSIONS.size + 1000}`)  // @@T decoy pii_log only the generated numeric id is logged
  return response.created({ ok: true })
})
