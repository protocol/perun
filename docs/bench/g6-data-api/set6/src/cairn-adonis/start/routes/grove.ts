import router from '@adonisjs/core/services/router'
import logger from '@adonisjs/core/services/logger'
import { Agent, fetch as ufetch } from 'undici'
import { middleware } from '#start/kernel'
import { costLimit } from '#start/limiter'
import { safeEq } from '#services/compare'
import { ROWS, SESSIONS, labels, openSession, ownedOrNull } from '#services/store'
import { BASE, KEY, MODEL, chat, sms, tool, vget, vpost } from '#services/vendor'

router.post('/api/ext/numbat/track', async ({ me }) => {  // @@R POST /api/ext/numbat/track 1
  await vpost('https://stats.vendor.example.com/v1/event', JSON.stringify({ event: 'view', email: me.email, phone: me.phone }))  // @@T positive pii_data raw email and phone sent to a third-party analytics host
  return { ok: true }
}).use(middleware.auth())

router.post('/api/ext/oriole/share', async ({ me }) => {  // @@R POST /api/ext/oriole/share 1
  await vpost('https://stats.vendor.example.com/v1/profile', JSON.stringify({ email: me.email, dob: '1984-03-09' }))  // @@T positive pii_data raw email and birth date sent to a third-party host
  return { ok: true }
}).use(middleware.auth())

router.get('/api/ext/rail/ping', async () => {  // @@R GET /api/ext/rail/ping 1
  return { ok: true }
}).use(middleware.auth())

const SEED_MOLE = [{ name: 'Jane Smith', email: 'jane@example.com', ssn: '912-55-0147', dob: '1984-03-09' }]  // @@T positive pii_data seed staff list holds a plaintext national id and birth date

router.get('/api/ext/mole/sample', async () => {  // @@R GET /api/ext/mole/sample 1
  return { count: SEED_MOLE.length }
}).use(middleware.auth())

router.get('/api/ext/pansy/ping', async () => {  // @@R GET /api/ext/pansy/ping 1
  return { ok: true }
}).use(middleware.auth())

const SEED_OKAPI = [{ label: 'Sample cairn', region: 'north', count: 3 }]  // @@T decoy pii_data seed rows hold labels and counts and no person

router.get('/api/ext/okapi/sample', async () => {  // @@R GET /api/ext/okapi/sample 1
  return { count: SEED_OKAPI.length }
}).use(middleware.auth())

router.get('/api/ext/quail/ping', async () => {  // @@R GET /api/ext/quail/ping 1
  return { ok: true }
}).use(middleware.auth())

router.post('/api/ext/pika/track', async () => {  // @@R POST /api/ext/pika/track 1
  await vpost('https://stats.vendor.example.com/v1/event', JSON.stringify({ event: 'view' }))  // @@T decoy pii_data analytics payload is a constant event name with no user identifier
  return { ok: true }
}).use(middleware.auth())
