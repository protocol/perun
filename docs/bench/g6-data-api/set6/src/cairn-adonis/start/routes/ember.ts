import router from '@adonisjs/core/services/router'
import logger from '@adonisjs/core/services/logger'
import { Agent, fetch as ufetch } from 'undici'
import { middleware } from '#start/kernel'
import { costLimit } from '#start/limiter'
import { safeEq } from '#services/compare'
import { ROWS, SESSIONS, labels, openSession, ownedOrNull } from '#services/store'
import { BASE, KEY, MODEL, chat, sms, tool, vget, vpost } from '#services/vendor'

router.post('/web/ext/bongo/phone', async ({ me, request, response }) => {  // @@R POST /web/ext/bongo/phone 1
  if (!safeEq(request.header('x-csrf-token') ?? '', me.csrf)) {  // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
    return response.forbidden({ error: 'csrf' })
  }
  return { updated: String(request.input('phone', '')).length <= 20 }
}).use(middleware.auth())

router.post('/web/ext/civet/nickname', async ({ me, request, response }) => {  // @@R POST /web/ext/civet/nickname 1
  if (!safeEq(request.header('x-csrf-token') ?? '', me.csrf)) {  // @@T decoy csrf header token is compared in constant time with the token stored on the server session and a missing header is rejected
    return response.forbidden({ error: 'csrf' })
  }
  return { updated: String(request.input('nickname', '')).length > 0 }
}).use(middleware.auth())

router.get('/web/pref/mimosa/layout', async () => {  // @@R GET /web/pref/mimosa/layout 1
  return { layout: 'wide' }
}).use(middleware.auth())

router.post('/web/ext/zebu/email', async ({ me, request }) => {  // @@R POST /web/ext/zebu/email 1
  const email = String(request.input('email', '')).slice(0, 120)  // @@T positive csrf cookie-session email change accepted with no anti-forgery token
  if (email) me.email = email
  return { updated: email.length > 0 }
}).use(middleware.auth())

router.post('/web/ext/agama/close', async ({ token, response }) => {  // @@R POST /web/ext/agama/close 1
  SESSIONS.delete(token)  // @@T positive csrf cookie-session account closure reachable from a cross-site form post
  response.clearCookie('sid', { httpOnly: true, secure: true, sameSite: 'strict' })
  return response.noContent()
}).use(middleware.auth())

router.get('/web/ext/dingo/remember', async ({ me, response }) => {  // @@R GET /web/ext/dingo/remember 1
  response.cookie('sid', openSession(me.uid, 'clerk'), { httpOnly: false, secure: false, sameSite: false })  // @@T positive cookie_flags session cookie issued with httpOnly secure and sameSite all switched off
  return response.noContent()
}).use(middleware.auth())

router.get('/web/pref/nigella/locale', async () => {  // @@R GET /web/pref/nigella/locale 1
  return { locale: 'en' }
}).use(middleware.auth())

router.get('/web/ext/hyrax/keep', async ({ me, response }) => {  // @@R GET /web/ext/hyrax/keep 1
  response.cookie('keep', openSession(me.uid, 'clerk'), { sameSite: 'strict', secure: true, httpOnly: true, maxAge: '1h' })  // @@T decoy cookie_flags httpOnly secure and sameSite strict set together with a one hour lifetime
  return response.noContent()
}).use(middleware.auth())

router.post('/web/ext/gecko/rotate', async ({ me, request, response }) => {  // @@R POST /web/ext/gecko/rotate 1
  if (!safeEq(request.header('x-csrf-token') ?? '', me.csrf)) return response.forbidden({ error: 'csrf' })
  response.cookie('sid', openSession(me.uid, me.role), { httpOnly: true, secure: true, sameSite: 'strict', maxAge: '1h' })  // @@T decoy cookie_flags the new session cookie is secure httpOnly and sameSite strict with a one hour lifetime
  return response.noContent()
}).use(middleware.auth())

router.get('/web/pref/lotus/theme', async ({ me }) => {  // @@R GET /web/pref/lotus/theme 1
  return { theme: 'light', uid: me.uid }
}).use(middleware.auth())

router.post('/web/ext/osprey/address', async ({ request }) => {  // @@R POST /web/ext/osprey/address 1
  const address = String(request.input('address', '')).slice(0, 200)  // @@T positive csrf cookie-session address change accepted with no anti-forgery token
  return { updated: address.length > 0 }
}).use(middleware.auth())

router.get('/web/ext/eland/trust', async ({ me, response }) => {  // @@R GET /web/ext/eland/trust 1
  response.cookie('trust', openSession(me.uid, 'clerk'), { httpOnly: false, secure: true, sameSite: 'lax', maxAge: '1d' })  // @@T positive cookie_flags login token cookie readable from script because httpOnly is false
  return response.noContent()
}).use(middleware.auth())
