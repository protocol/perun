import router from '@adonisjs/core/services/router'
import logger from '@adonisjs/core/services/logger'
import { Agent, fetch as ufetch } from 'undici'
import { middleware } from '#start/kernel'
import { costLimit } from '#start/limiter'
import { safeEq } from '#services/compare'
import { ROWS, SESSIONS, labels, openSession, ownedOrNull } from '#services/store'
import { BASE, KEY, MODEL, chat, sms, tool, vget, vpost } from '#services/vendor'

router.get('/api/ext/urchin/:code/rates', async ({ params, response }) => {  // @@R GET /api/ext/urchin/:code/rates 1
  if (!/^[A-Z]{2}$/.test(params.code)) return response.badRequest()
  const res = await vget(`${BASE}/v1/rates/${params.code}`, { 'X-Api-Key': KEY })  // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
  return res.text()
}).use(middleware.auth())

router.get('/api/ext/linnet/ping', async () => {  // @@R GET /api/ext/linnet/ping 1
  return { ok: true }
}).use(middleware.auth())

router.get('/api/ext/quokka/lookup', async () => {  // @@R GET /api/ext/quokka/lookup 1
  const res = await vget(`${BASE}/v1/quokka?key=${KEY}`)  // @@T positive secret_in_url vendor key sent as a query parameter
  return { status: res.status }
}).use(middleware.auth())

router.get('/api/ext/raven/ping', async () => {  // @@R GET /api/ext/raven/ping 1
  logger.info(`vendor ping key=${KEY}`)  // @@T positive secret_in_log vendor key written to the application log
  const res = await vget(`${BASE}/v1/ping`, { 'X-Api-Key': KEY })
  return { status: res.status }
}).use(middleware.auth())

router.get('/api/ext/wisent/ping', async () => {  // @@R GET /api/ext/wisent/ping 1
  return { ok: true }
}).use(middleware.auth())

router.post('/api/ext/wombat/summarise', async ({ request }) => {  // @@R POST /api/ext/wombat/summarise 1
  const note = String(request.input('note', '')).slice(0, 500)
  return { reply: await chat([{ role: 'system', content: 'You summarise cairn notes and have no tools.' }, { role: 'user', content: note }]) }  // @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
}).use(middleware.auth())

router.get('/api/ext/crake/ping', async () => {  // @@R GET /api/ext/crake/ping 1
  return { ok: true }
}).use(middleware.auth())

router.post('/api/ext/xerus/summarise', async ({ request }) => {  // @@R POST /api/ext/xerus/summarise 1
  const note = String(request.input('note', '')).slice(0, 500)
  return { reply: await chat([{ role: 'system', content: 'You summarise cairn notes and have no tools.' }, { role: 'user', content: note }]) }  // @@T decoy rate_limit model call route uses the cost limiter middleware that caps each client address at twenty requests a minute
}).use([middleware.auth(), costLimit])

router.get('/api/ext/drongo/ping', async () => {  // @@R GET /api/ext/drongo/ping 1
  return { ok: true }
}).use(middleware.auth())

router.get('/api/ext/shrike/notify', async () => {  // @@R GET /api/ext/shrike/notify 1
  const headers = { 'X-Api-Key': KEY }
  logger.info({ headers }, 'vendor status request')  // @@T positive secret_in_log request headers carrying the vendor key written to the application log
  const res = await vget(`${BASE}/v1/notify/status`, headers)
  return { status: res.status }
}).use(middleware.auth())

router.get('/api/ext/egret/ping', async () => {  // @@R GET /api/ext/egret/ping 1
  return { ok: true }
}).use(middleware.auth())

router.post('/api/ext/yak/notify', async ({ me }) => {  // @@R POST /api/ext/yak/notify 1
  return { status: await sms(me.phone, 'Your cairn parcel has shipped.') }  // @@T decoy rate_limit sms send route uses the cost limiter middleware that caps each client address at twenty requests a minute
}).use([middleware.auth(), costLimit])

router.get('/api/ext/godwit/ping', async () => {  // @@R GET /api/ext/godwit/ping 1
  return { ok: true }
}).use(middleware.auth())

router.get('/api/ext/vireo/export', async ({ me }) => {  // @@R GET /api/ext/vireo/export 1
  return { rows: labels([...ROWS.values()].filter((row) => row.owner === me.uid)), exportedAt: new Date().toISOString() }  // @@T positive rate_limit bulk export route has no limiter so one client can pull the whole export repeatedly
}).use(middleware.auth())

router.get('/api/ext/finch/ping', async () => {  // @@R GET /api/ext/finch/ping 1
  return { ok: true }
}).use(middleware.auth())

router.get('/api/ext/hobby/ping', async () => {  // @@R GET /api/ext/hobby/ping 1
  return { ok: true }
}).use(middleware.auth())
