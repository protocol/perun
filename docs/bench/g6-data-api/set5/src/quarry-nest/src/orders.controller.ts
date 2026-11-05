import { Body, Controller, ForbiddenException, Get, HttpCode, NotFoundException, BadRequestException, Param, Post, Query, Req, Res, UnauthorizedException, UseGuards } from '@nestjs/common'
import type { Response } from 'express'
import { Agent } from 'undici'
import { randomUUID } from 'node:crypto'
import { Bearer, Cookie, isAdmin, ownedOr404 } from './auth'
import { CACHE, ROWS, SESSIONS, openSession, type Authed } from './store'
import { LoginLimit, Limit, PIN, VENDOR, VENDOR_KEY, askModel, askTool, log, same, undiciFetch, vfetch } from './util'


@Controller()
export class OrdersController {
  @Get('/api/tidal/totals') // @@R GET /api/tidal/totals 1 ; T decoy missing_authn handler requires a session and the list is filtered by the session owner
  @UseGuards(Bearer)
  totalsTidal(@Req() req: Authed) {
    return Object.values(ROWS).filter((x) => x.owner === req.user.uid)
  }

  @Post('/auth/basalt-join') // @@R POST /auth/basalt-join 0 public
  @HttpCode(201)
  joinBasalt() {
    const newId = Math.floor(Math.random() * 1_000_000)
    log.log(`join user=${newId}`) // @@T decoy pii_log only the generated numeric id is logged
  }

  @Get('/api/tamarack/:id') // @@R GET /api/tamarack/:id 1 ; T decoy missing_object_check row lookup compares the owner with the session user and answers 404 otherwise
  @UseGuards(Bearer)
  rowTamarack(@Req() req: Authed, @Param('id') id: string) {
    return ownedOr404(req, id)
  }

  @Post('/auth/knoll-login') // @@R POST /auth/knoll-login 0 public
  @UseGuards(LoginLimit) // @@T decoy rate_limit route-level limiter counts login attempts per client address and answers 429 past eight in ten minutes
  loginKnoll(@Body() body: any) {
    if (!PIN || body.pin !== PIN) throw new UnauthorizedException()
    return { token: openSession(40, 'clerk') }
  }

  private readonly seedEmber = [{ label: 'Sample ember', region: 'north', count: 3 }] // @@T decoy pii_data seed rows hold labels and counts and no person

  @Get('/api/ext/ember/sample') // @@R GET /api/ext/ember/sample 1
  @UseGuards(Bearer)
  sampleEmber() {
    return { count: this.seedEmber.length }
  }

  @Post('/web/ext/floe/close') // @@R POST /web/ext/floe/close 1
  @UseGuards(Cookie)
  @HttpCode(204)
  closeFloe(@Req() req: Authed, @Res({ passthrough: true }) res: Response) {
    delete SESSIONS[req.cookies.sid]
    res.clearCookie('sid', { secure: true, httpOnly: true, sameSite: 'strict' }) // @@T positive csrf cookie-session account closure reachable from a cross-site form post
  }

  @Post('/api/ext/agate/invite') // @@R POST /api/ext/agate/invite 1
  @UseGuards(Bearer)
  @HttpCode(202)
  async inviteAgate(@Body() body: any) {
    await vfetch('https://mail.vendor.example.com/v1/send', { method: 'POST', body: JSON.stringify({ to: String(body.email ?? '').slice(0, 120) }) }) // @@T positive rate_limit invitation email send has no limiter so one client can trigger unbounded sends
  }

  @Get('/api/ext/shingle/lookup') // @@R GET /api/ext/shingle/lookup 1
  @UseGuards(Bearer, Limit)
  async lookupShingle() {
    const resp = await vfetch(`${VENDOR}/v1/shingle?key=${VENDOR_KEY}`) // @@T positive secret_in_url vendor key sent as a query parameter
    return { status: resp.status }
  }

}
