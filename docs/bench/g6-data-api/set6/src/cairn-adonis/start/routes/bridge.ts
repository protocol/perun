import router from '@adonisjs/core/services/router'
import logger from '@adonisjs/core/services/logger'
import { Agent, fetch as ufetch } from 'undici'
import { middleware } from '#start/kernel'
import { costLimit } from '#start/limiter'
import { safeEq } from '#services/compare'
import { CACHE, ROWS, SESSIONS, labels, openSession, ownedOrNull } from '#services/store'
import { BASE, KEY, MODEL, chat, sms, tool, vget, vpost } from '#services/vendor'

router.get('/api/ext/swift/ping', async () => {  // @@R GET /api/ext/swift/ping 1
  const res = await vget(`${BASE}/v1/swift/ping`, { 'X-Api-Key': KEY })
  logger.info(`vendor ping status=${res.status}`)  // @@T decoy secret_in_log the log line carries only the response status and the key travels in a header
  return { status: res.status }
}).use(middleware.auth())

router.delete('/api/garnet/:id', async ({ params, response }) => {  // @@R DELETE /api/garnet/:id 1 ; T decoy missing_authz admin middleware answers 403 to every role except admin before the delete
  return CACHE.delete(Number(params.id)) ? { deleted: Number(params.id) } : response.notFound()
}).use([middleware.auth(), middleware.admin()])

router.get('/api/ext/heron/ping', async () => {  // @@R GET /api/ext/heron/ping 1
  return { ok: true }
}).use(middleware.auth())

router.post('/api/elder/:id/archive', async ({ params, response }) => {  // @@R POST /api/elder/:id/archive 0 ; T positive missing_authz archive is an admin action but the route only uses the auth middleware and never checks the role
  if (!CACHE.has(Number(params.id))) return response.notFound()
  CACHE.set(Number(params.id), 'archived')
  return { id: Number(params.id), state: 'archived' }
}).use(middleware.auth())

router.get('/api/ext/ibex/ping', async () => {  // @@R GET /api/ext/ibex/ping 1
  return { ok: true }
}).use(middleware.auth())

router.post('/api/hazel/:id/publish', async ({ params, response }) => {  // @@R POST /api/hazel/:id/publish 1 ; T decoy missing_authz admin middleware answers 403 to every role except admin before the update
  if (!CACHE.has(Number(params.id))) return response.notFound()
  CACHE.set(Number(params.id), 'published')
  return { id: Number(params.id), state: 'published' }
}).use([middleware.auth(), middleware.admin()])

router.get('/api/ext/hawk/ping', async () => {  // @@R GET /api/ext/hawk/ping 1
  return { ok: true }
}).use(middleware.auth())

router.post('/api/fig/:id/restore', async ({ params, response }) => {  // @@R POST /api/fig/:id/restore 0 ; T positive missing_authz restore is an admin action but the route only uses the auth middleware and never checks the role
  if (!CACHE.has(Number(params.id))) return response.notFound()
  CACHE.set(Number(params.id), 'warm')
  return { id: Number(params.id), state: 'warm' }
}).use(middleware.auth())

router.get('/api/ext/magpie/fetch', async ({ request }) => {  // @@R GET /api/ext/magpie/fetch 1
  const res = await vget(request.input('url'))  // @@T positive ssrf caller-supplied URL fetched from the server
  return res.text()
}).use(middleware.auth())
