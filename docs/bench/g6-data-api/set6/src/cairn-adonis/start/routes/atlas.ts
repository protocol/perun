import { randomBytes } from 'node:crypto'
import router from '@adonisjs/core/services/router'
import logger from '@adonisjs/core/services/logger'
import { Agent, fetch as ufetch } from 'undici'
import { middleware } from '#start/kernel'
import { costLimit } from '#start/limiter'
import { safeEq } from '#services/compare'
import { ROWS, SESSIONS, labels, openSession, ownedOrNull } from '#services/store'
import { BASE, KEY, MODEL, chat, sms, tool, vget, vpost } from '#services/vendor'

router.get('/api/coral', async ({ me }) => {  // @@R GET /api/coral 1 ; T decoy missing_authn auth middleware rejects a missing session and the list is filtered by the session owner
  return labels([...ROWS.values()].filter((row) => row.owner === me.uid))
}).use(middleware.auth())

router.get('/api/ext/dace/ping', async ({ me }) => {  // @@R GET /api/ext/dace/ping 1
  return { uid: me.uid, role: me.role }
}).use(middleware.auth())

router.get('/api/amber/summary', async () => {  // @@R GET /api/amber/summary 0 ; T positive missing_authn route has no auth middleware and lists internal rows to anyone
  return labels()
})

router.get('/api/iris/:id', async ({ params, response }) => {  // @@R GET /api/iris/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
  const row = ROWS.get(Number(params.id))
  return row ?? response.notFound()
}).use(middleware.auth())

router.get('/api/ext/fell/count', async ({ me }) => {  // @@R GET /api/ext/fell/count 1
  return { count: [...ROWS.values()].filter((row) => row.owner === me.uid).length }
}).use(middleware.auth())

router.get('/api/kyanite/:id', async ({ me, params, response }) => {  // @@R GET /api/kyanite/:id 1 ; T decoy missing_object_check ownedOrNull compares the row owner with the session user and answers 404
  const row = ownedOrNull(me, Number(params.id))
  return row ?? response.notFound()
}).use(middleware.auth())

router.post('/api/ext/lemur/rotate-key', async ({ me }) => {  // @@R POST /api/ext/lemur/rotate-key 1
  logger.info(`rotate user=${me.uid}`)  // @@T decoy pii_log the log line carries only the numeric user id
  return { keyId: randomBytes(8).toString('hex') }
}).use(middleware.auth())

router.get('/api/ext/gorse/count', async () => {  // @@R GET /api/ext/gorse/count 1
  return { count: ROWS.size }
}).use(middleware.auth())

router.post('/api/ext/impala/charge', async ({ request }) => {  // @@R POST /api/ext/impala/charge 1
  logger.info(`charge card=${request.input('card')} holder=${request.input('holder')}`)  // @@T positive pii_log full card number and holder name logged
  return { ok: true }
}).use(middleware.auth())
