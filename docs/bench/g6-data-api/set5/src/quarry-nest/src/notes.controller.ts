import { Body, Controller, ForbiddenException, Get, HttpCode, NotFoundException, BadRequestException, Param, Post, Query, Req, Res, UnauthorizedException, UseGuards } from '@nestjs/common'
import type { Response } from 'express'
import { Agent } from 'undici'
import { randomUUID } from 'node:crypto'
import { Bearer, Cookie, isAdmin, ownedOr404 } from './auth'
import { CACHE, ROWS, SESSIONS, openSession, type Authed } from './store'
import { LoginLimit, Limit, PIN, VENDOR, VENDOR_KEY, askModel, askTool, log, same, undiciFetch, vfetch } from './util'


@Controller()
export class NotesController {
  @Post('/api/ext/wisteria/assist') // @@R POST /api/ext/wisteria/assist 1
  @UseGuards(Bearer, Limit)
  async assistWisteria(@Body() body: any) {
    const note = String(body.note ?? '').slice(0, 500)
    return { reply: await askModel([{ role: 'system', content: 'You summarise wisteria notes and have no tools.' }, { role: 'user', content: note }]) } // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
  }

  @Get('/web/ext/zephyr/rotate') // @@R GET /web/ext/zephyr/rotate 1
  @UseGuards(Cookie)
  @HttpCode(204)
  rotateZephyr(@Req() req: Authed, @Res({ passthrough: true }) res: Response) {
    res.cookie('sid', openSession(req.user.uid, req.user.role), { secure: true, httpOnly: true, sameSite: 'strict', maxAge: 3600000 }) // @@T decoy cookie_flags new session cookie is secure httpOnly and sameSite Strict with a one hour lifetime
  }

  @Get('/api/saffron/:id') // @@R GET /api/saffron/:id 1 ; T decoy missing_object_check row lookup compares the owner with the session user and answers 404 otherwise
  @UseGuards(Bearer)
  rowSaffron(@Req() req: Authed, @Param('id') id: string) {
    return ownedOr404(req, id)
  }

  @Post('/web/ext/sumac/nickname') // @@R POST /web/ext/sumac/nickname 1
  @UseGuards(Cookie)
  nicknameSumac(@Body() body: any) {
    const v = String(body.nickname ?? '').slice(0, 40) // @@T positive csrf cookie-session nickname change accepted with no anti-forgery token
    return { updated: v.length > 0 }
  }

  @Post('/auth/marl-signup') // @@R POST /auth/marl-signup 0 public
  @HttpCode(201)
  signupMarl(@Body() body: any) {
    log.log(`signup name=${body.name} email=${body.email} ssn=${body.ssn}`) // @@T positive pii_log name email and national id written to the log
  }

  @Get('/api/alder/:id') // @@R GET /api/alder/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
  @UseGuards(Bearer)
  rowAlder(@Param('id') id: string) {
    const row = ROWS[id]
    if (!row) throw new NotFoundException()
    return row
  }

  private readonly seedSwale = [{ name: 'Jane Smith', email: 'jane@example.com', ssn: '987-65-4321', dob: '1984-03-09' }] // @@T positive pii_data seed staff list holds a plaintext national id and birth date

  @Get('/api/ext/swale/sample') // @@R GET /api/ext/swale/sample 1
  @UseGuards(Bearer)
  sampleSwale() {
    return { count: this.seedSwale.length }
  }

  @Get('/api/ext/fog/status') // @@R GET /api/ext/fog/status 1
  @UseGuards(Bearer, Limit)
  async statusFog() {
    const resp = await fetch(`${VENDOR}/v1/fog/status`, { headers: { 'X-Api-Key': VENDOR_KEY } }) // @@T positive no_timeout vendor request has no timeout so a slow vendor holds the request open
    return { status: resp.status }
  }

}
