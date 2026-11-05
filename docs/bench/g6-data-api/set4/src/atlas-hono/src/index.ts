import { serve } from '@hono/node-server'
import { Hono } from 'hono'
import type { MiddlewareHandler } from 'hono'
import { bearerAuth, cookieAuth } from './auth'
import type { Env } from './store'
import { throttle } from './util'
import assist from './routes/assist'
import copilot from './routes/copilot'
import catalog from './routes/catalog'
import desk from './routes/desk'
import gateway from './routes/gateway'
import integrations from './routes/integrations'
import partners from './routes/partners'
import people from './routes/people'
import members from './routes/members'
import publicRoutes from './routes/public'
import records from './routes/records'
import web from './routes/web'
import console from './routes/console'

const app = new Hono<Env>()

// register each router's routes with exactly the middleware listed for its group
const mount = (sub: Hono<Env>, ...mw: MiddlewareHandler<Env>[]) =>
  sub.routes.forEach((rt) => app.on(rt.method, rt.path, ...mw, rt.handler as MiddlewareHandler<Env>))

const me = new Hono<Env>()
me.get('/api/me', (c) => c.json({ uid: c.get('user').uid, role: c.get('user').role })) // @@R GET /api/me 1

const limit = throttle(60, 60_000)
mount(publicRoutes)
mount(gateway)
mount(desk, bearerAuth)
for (const r of [me, records, catalog, partners, integrations, people, members, assist, copilot]) mount(r, bearerAuth, limit)
for (const r of [web, console]) mount(r, cookieAuth, limit)

serve({ fetch: app.fetch, port: 3000, hostname: '127.0.0.1' })
