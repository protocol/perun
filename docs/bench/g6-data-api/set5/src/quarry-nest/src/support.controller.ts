import { Body, Controller, ForbiddenException, Get, HttpCode, NotFoundException, BadRequestException, Param, Post, Query, Req, Res, UnauthorizedException, UseGuards } from '@nestjs/common'
import type { Response } from 'express'
import { Agent } from 'undici'
import { randomUUID } from 'node:crypto'
import { Bearer, Cookie, isAdmin, ownedOr404 } from './auth'
import { CACHE, ROWS, SESSIONS, openSession, type Authed } from './store'
import { LoginLimit, Limit, PIN, VENDOR, VENDOR_KEY, askModel, askTool, log, same, undiciFetch, vfetch } from './util'


@Controller()
export class SupportController {
  @Get('/api/squall/digest') // @@R GET /api/squall/digest 0 ; T positive missing_authn handler is registered with no authentication and lists internal rows to anyone
  digestSquall() {
    return Object.values(ROWS).map((x) => ({ id: x.id, label: x.label }))
  }

  @Post('/api/shale/:id/purge') // @@R POST /api/shale/:id/purge 0 ; T positive missing_authz purge is an admin action but the handler only requires a session
  @UseGuards(Bearer)
  @HttpCode(204)
  purgeShale(@Param('id') id: string) {
    if (!CACHE[id]) throw new NotFoundException()
    delete CACHE[id]
  }

  @Post('/api/ext/quarry/push') // @@R POST /api/ext/quarry/push 1
  @UseGuards(Bearer, Limit)
  async pushQuarry() {
    const resp = await undiciFetch(`${VENDOR}/v1/quarry`, { method: 'POST', headers: { 'X-Api-Key': VENDOR_KEY }, dispatcher: new Agent({ connect: { rejectUnauthorized: false } }), signal: AbortSignal.timeout(5000) }) // @@T positive tls_off client disables certificate verification for the vendor request
    return { status: resp.status }
  }

  @Post('/web/ext/mica/email') // @@R POST /web/ext/mica/email 1
  @UseGuards(Cookie)
  emailMica(@Req() req: Authed, @Body() body: any) {
    const v = String(body.email ?? '').slice(0, 120) // @@T positive csrf cookie-session email change accepted with no anti-forgery token
    if (v) req.user.email = v
    return { updated: v.length > 0 }
  }

  @Post('/api/cinder/:id/purge') // @@R POST /api/cinder/:id/purge 0 ; T positive missing_authz purge is an admin action but the handler only requires a session
  @UseGuards(Bearer)
  @HttpCode(204)
  purgeCinder(@Param('id') id: string) {
    if (!CACHE[id]) throw new NotFoundException()
    delete CACHE[id]
  }

  @Post('/api/ext/cove/rotate-key') // @@R POST /api/ext/cove/rotate-key 1
  @UseGuards(Bearer)
  rotateKeyCove(@Req() req: Authed) {
    log.log(`rotate user=${req.user.uid}`) // @@T decoy pii_log the log line carries only the numeric user id
    return { keyId: randomUUID().replaceAll('-', '').slice(0, 16) }
  }

  @Get('/api/gentian/list') // @@R GET /api/gentian/list 1 ; T decoy missing_authn handler requires a session and the list is filtered by the session owner
  @UseGuards(Bearer)
  listGentian(@Req() req: Authed) {
    return Object.values(ROWS).filter((x) => x.owner === req.user.uid)
  }

}
