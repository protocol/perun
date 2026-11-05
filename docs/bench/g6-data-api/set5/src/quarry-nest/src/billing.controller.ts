import { Body, Controller, ForbiddenException, Get, HttpCode, NotFoundException, BadRequestException, Param, Post, Query, Req, Res, UnauthorizedException, UseGuards } from '@nestjs/common'
import type { Response } from 'express'
import { Agent } from 'undici'
import { randomUUID } from 'node:crypto'
import { Bearer, Cookie, isAdmin, ownedOr404 } from './auth'
import { CACHE, ROWS, SESSIONS, openSession, type Authed } from './store'
import { LoginLimit, Limit, PIN, VENDOR, VENDOR_KEY, askModel, askTool, log, same, undiciFetch, vfetch } from './util'


@Controller()
export class BillingController {
  @Get('/web/ext/bluebell/trust') // @@R GET /web/ext/bluebell/trust 1
  @UseGuards(Cookie)
  @HttpCode(204)
  trustBluebell(@Req() req: Authed, @Res({ passthrough: true }) res: Response) {
    res.cookie('trust', openSession(req.user.uid, req.user.role), { secure: true, sameSite: 'lax', maxAge: 86400000 }) // @@T positive cookie_flags session cookie readable from script because httpOnly is not set
  }

  @Post('/api/ext/ridgeway/lookup-tool') // @@R POST /api/ext/ridgeway/lookup-tool 1
  @UseGuards(Bearer, Limit)
  async toolRidgeway(@Body() body: any) {
    return { reply: await askTool(`{"tool": "lookup", "arg": "${body.arg}"}`) } // @@T positive prompt_injection request value formatted into raw tool-call JSON
  }

  @Post('/api/ext/dapple/push') // @@R POST /api/ext/dapple/push 1
  @UseGuards(Bearer, Limit)
  async pushDapple() {
    const resp = await undiciFetch(`${VENDOR}/v1/dapple`, { method: 'POST', headers: { 'X-Api-Key': VENDOR_KEY }, dispatcher: new Agent({ connect: { rejectUnauthorized: false } }), signal: AbortSignal.timeout(5000) }) // @@T positive tls_off client disables certificate verification for the vendor request
    return { status: resp.status }
  }

  @Post('/api/ext/lupine/lookup-tool') // @@R POST /api/ext/lupine/lookup-tool 1
  @UseGuards(Bearer, Limit)
  async toolLupine(@Body() body: any) {
    return { reply: await askTool(JSON.stringify({ tool: 'lookup', arg: String(body.sku ?? '') })) } // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
  }

  @Post('/api/narrows/:id/purge') // @@R POST /api/narrows/:id/purge 1 ; T decoy missing_authz handler answers 403 unless the session role is admin before the delete
  @UseGuards(Bearer)
  @HttpCode(204)
  purgeNarrows(@Req() req: Authed, @Param('id') id: string) {
    if (!isAdmin(req)) throw new ForbiddenException()
    if (!CACHE[id]) throw new NotFoundException()
    delete CACHE[id]
  }

  @Get('/api/ext/cypress/:code/stock') // @@R GET /api/ext/cypress/:code/stock 1
  @UseGuards(Bearer, Limit)
  async stockCypress(@Param('code') code: string) {
    if (!/^[A-Z]{2}$/.test(code)) throw new BadRequestException()
    const resp = await vfetch(`${VENDOR}/v1/stock/${code}`, { headers: { 'X-Api-Key': VENDOR_KEY } })
    log.log(`stock lookup code=${code} status=${resp.status}`) // @@T decoy secret_in_log only the status and the validated code are logged
    return resp.json()
  }

  @Get('/web/ext/stoat/keep') // @@R GET /web/ext/stoat/keep 1
  @UseGuards(Cookie)
  @HttpCode(204)
  keepStoat(@Res({ passthrough: true }) res: Response) {
    res.cookie('keep', randomUUID(), { httpOnly: true, secure: true, sameSite: 'strict', maxAge: 3600000 }) // @@T decoy cookie_flags cookie sets httpOnly secure and sameSite Strict together with a one hour lifetime
  }

  @Post('/web/ext/onyx/phone') // @@R POST /web/ext/onyx/phone 1
  @UseGuards(Cookie)
  phoneOnyx(@Req() req: Authed, @Body() body: any) {
    if (!same(req.header('x-csrf-token') ?? '', req.user.csrf)) throw new ForbiddenException() // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
    return { updated: String(body.phone ?? '').length <= 20 }
  }

}
