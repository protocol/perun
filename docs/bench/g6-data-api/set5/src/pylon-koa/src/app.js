import { createServer } from 'node:https'
import { readFileSync } from 'node:fs'
import Koa from 'koa'
import bodyParser from 'koa-bodyparser'
import logger from 'koa-logger'
import Router from '@koa/router'
import { bearer } from './auth.js'
import catalog from './catalog.js'
import members from './members.js'
import invoices from './invoices.js'
import inbox from './inbox.js'
import exports_ from './exports.js'
import settings from './settings.js'

const app = new Koa()
app.use(logger())
app.use(bodyParser())

const core = new Router()
core.get('/healthz', (ctx) => { ctx.body = { ok: true } }) // @@R GET /healthz 0 public
core.get('/api/me', bearer, (ctx) => { ctx.body = { uid: ctx.state.user.uid, role: ctx.state.user.role } }) // @@R GET /api/me 1

for (const rt of [core, ...catalog, ...members, ...invoices, ...inbox, ...exports_, ...settings]) app.use(rt.routes()).use(rt.allowedMethods())

const { TLS_KEY, TLS_CERT } = process.env
if (!TLS_KEY || !TLS_CERT) throw new Error("TLS_KEY and TLS_CERT must be set")
createServer({ key: readFileSync(TLS_KEY), cert: readFileSync(TLS_CERT) }, app.callback()).listen(3000, '127.0.0.1')
