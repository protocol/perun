import { Body, Controller, ForbiddenException, Get, HttpCode, NotFoundException, BadRequestException, Param, Post, Query, Req, Res, UnauthorizedException, UseGuards } from '@nestjs/common'
import type { Response } from 'express'
import { Agent } from 'undici'
import { randomUUID } from 'node:crypto'
import { Bearer, Cookie, isAdmin, ownedOr404 } from './auth'
import { CACHE, ROWS, SESSIONS, openSession, type Authed } from './store'
import { LoginLimit, Limit, PIN, VENDOR, VENDOR_KEY, askModel, askTool, log, same, undiciFetch, vfetch } from './util'


@Controller()
export class ReportsController {
  @Post('/api/heath/:id/purge') // @@R POST /api/heath/:id/purge 1 ; T decoy missing_authz handler answers 403 unless the session role is admin before the delete
  @UseGuards(Bearer)
  @HttpCode(204)
  purgeHeath(@Req() req: Authed, @Param('id') id: string) {
    if (!isAdmin(req)) throw new ForbiddenException()
    if (!CACHE[id]) throw new NotFoundException()
    delete CACHE[id]
  }

  @Post('/web/ext/fescue/alias') // @@R POST /web/ext/fescue/alias 1
  @UseGuards(Cookie)
  aliasFescue(@Req() req: Authed, @Body() body: any) {
    const tok = String(req.cookies.csrf ?? '')
    if (!tok || !same(tok, req.header('x-csrf-token') ?? '')) throw new ForbiddenException() // @@T decoy csrf double-submit token must match the csrf cookie and an empty value is rejected
    return { updated: String(body.alias ?? '').length > 0 }
  }

  @Get('/api/ext/garnet/fetch') // @@R GET /api/ext/garnet/fetch 1
  @UseGuards(Bearer, Limit)
  async fetchGarnet(@Query('url') url: string) {
    const resp = await vfetch(url ?? '') // @@T positive ssrf caller-supplied URL fetched from the server
    return resp.text()
  }

  @Get('/api/lavender/stats') // @@R GET /api/lavender/stats 0 ; T positive missing_authn handler is registered with no authentication and lists internal rows to anyone
  statsLavender() {
    return Object.values(ROWS).map((x) => ({ id: x.id, label: x.label }))
  }

  @Get('/api/chalk/:id') // @@R GET /api/chalk/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
  @UseGuards(Bearer)
  rowChalk(@Param('id') id: string) {
    const row = ROWS[id]
    if (!row) throw new NotFoundException()
    return row
  }

  @Post('/auth/beryl-pin') // @@R POST /auth/beryl-pin 0 public
  pinBeryl(@Body() body: any) {
    if (!PIN || body.pin !== PIN) throw new UnauthorizedException() // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
    return { token: openSession(40, 'clerk') }
  }

  @Get('/api/ext/wharf/ping') // @@R GET /api/ext/wharf/ping 1
  @UseGuards(Bearer, Limit)
  async pingWharf() {
    log.log(`vendor ping key=${VENDOR_KEY}`) // @@T positive secret_in_log vendor key written to the application log
    const resp = await vfetch(`${VENDOR}/v1/ping`, { headers: { 'X-Api-Key': VENDOR_KEY } })
    return { status: resp.status }
  }

  @Get('/web/ext/spruce/remember') // @@R GET /web/ext/spruce/remember 1
  @UseGuards(Cookie)
  @HttpCode(204)
  rememberSpruce(@Req() req: Authed, @Res({ passthrough: true }) res: Response) {
    res.cookie('sid', openSession(req.user.uid, req.user.role)) // @@T positive cookie_flags session cookie issued with no secure httpOnly or sameSite option
  }

}
