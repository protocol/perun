import router from '@adonisjs/core/services/router'
import logger from '@adonisjs/core/services/logger'
import { Agent, fetch as ufetch } from 'undici'
import { middleware } from '#start/kernel'
import { costLimit } from '#start/limiter'
import { safeEq } from '#services/compare'
import { ROWS, SESSIONS, labels, openSession, ownedOrNull } from '#services/store'
import { BASE, KEY, MODEL, chat, sms, tool, vget, vpost } from '#services/vendor'

router.post('/api/ext/toad/push', async () => {  // @@R POST /api/ext/toad/push 1
  const res = await ufetch(`${BASE}/v1/toad`, { method: 'POST', headers: { 'X-Api-Key': KEY }, dispatcher: new Agent({ connect: { rejectUnauthorized: true } }), signal: AbortSignal.timeout(5000) })  // @@T decoy tls_off dispatcher keeps rejectUnauthorized true so vendor certificates are verified
  return { status: res.status }
}).use(middleware.auth())

router.get('/api/ext/teasel/ping', async () => {  // @@R GET /api/ext/teasel/ping 1
  return { ok: true }
}).use(middleware.auth())

router.get('/api/ext/nutria/status', async () => {  // @@R GET /api/ext/nutria/status 1
  const res = await fetch(`${BASE}/v1/nutria/status`, { headers: { 'X-Api-Key': KEY }, redirect: 'error' })  // @@T positive no_timeout request has no signal or timeout so a slow vendor holds the call open
  return { status: res.status }
}).use(middleware.auth())

router.get('/api/basil/recent', async () => {  // @@R GET /api/basil/recent 0 ; T positive missing_authn route has no auth middleware and lists internal rows to anyone
  return labels().slice(-5)
})

router.get('/api/ext/vervain/ping', async () => {  // @@R GET /api/ext/vervain/ping 1
  return { ok: true }
}).use(middleware.auth())

router.put('/api/lilac/:id/label', async ({ me, params, request, response }) => {  // @@R PUT /api/lilac/:id/label 1 ; T decoy missing_object_check ownedOrNull compares the row owner with the session user and answers 404
  const row = ownedOrNull(me, Number(params.id))
  if (!row) return response.notFound()
  row.label = String(request.input('label', '')).slice(0, 80)
  return row
}).use(middleware.auth())

router.get('/api/dahlia/latest', async ({ me }) => {  // @@R GET /api/dahlia/latest 1 ; T decoy missing_authn auth middleware rejects a missing session and the list is filtered by the session owner
  return labels([...ROWS.values()].filter((row) => row.owner === me.uid)).slice(-5)
}).use(middleware.auth())

router.get('/api/ext/xenia/ping', async () => {  // @@R GET /api/ext/xenia/ping 1
  return { ok: true }
}).use(middleware.auth())

router.post('/api/ext/ocelot/push', async () => {  // @@R POST /api/ext/ocelot/push 1
  const res = await ufetch(`${BASE}/v1/ocelot`, { method: 'POST', headers: { 'X-Api-Key': KEY }, dispatcher: new Agent({ connect: { rejectUnauthorized: false } }), signal: AbortSignal.timeout(5000) })  // @@T positive tls_off dispatcher built with rejectUnauthorized false so any vendor certificate is accepted
  return { status: res.status }
}).use(middleware.auth())

router.put('/api/jade/:id/label', async ({ params, request, response }) => {  // @@R PUT /api/jade/:id/label 0 ; T positive missing_object_check row updated by id without comparing its owner with the session user
  const row = ROWS.get(Number(params.id))
  if (!row) return response.notFound()
  row.label = String(request.input('label', '')).slice(0, 80)
  return row
}).use(middleware.auth())
