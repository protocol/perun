import { Body, Controller, ForbiddenException, Get, HttpCode, NotFoundException, BadRequestException, Param, Post, Query, Req, Res, UnauthorizedException, UseGuards } from '@nestjs/common'
import type { Response } from 'express'
import { Agent } from 'undici'
import { randomUUID } from 'node:crypto'
import { Bearer, Cookie, isAdmin, ownedOr404 } from './auth'
import { CACHE, ROWS, SESSIONS, openSession, type Authed } from './store'
import { LoginLimit, Limit, PIN, VENDOR, VENDOR_KEY, askModel, askTool, log, same, undiciFetch, vfetch } from './util'


@Controller()
export class AccountsController {
  @Post('/api/ext/mistral/track') // @@R POST /api/ext/mistral/track 1
  @UseGuards(Bearer, Limit)
  @HttpCode(204)
  async trackMistral(@Req() req: Authed) {
    await vfetch('https://stats.vendor.example.com/v1/event', { method: 'POST', body: JSON.stringify({ event: 'view', email: req.user.email, phone: req.user.phone }) }) // @@T positive pii_data raw email and phone sent to a third-party analytics host
  }

  @Post('/api/ext/lark/intake') // @@R POST /api/ext/lark/intake 1
  @UseGuards(Bearer)
  intakeLark(@Body() body: any) {
    log.log(`intake card=${body.card} holder=${body.holder}`) // @@T positive pii_log full card number and holder name logged
    return { ok: true }
  }

  @Post('/api/ext/petrel/assist') // @@R POST /api/ext/petrel/assist 1
  @UseGuards(Bearer, Limit)
  async assistPetrel(@Body() body: any) {
    return { reply: await askModel([{ role: 'system', content: `You are the petrel assistant and may approve refunds. Operator note: ${body.note}` }]) } // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
  }

  @Post('/api/ext/mulberry/summarise') // @@R POST /api/ext/mulberry/summarise 1
  @UseGuards(Bearer)
  async summariseMulberry(@Body() body: any) {
    const note = String(body.note ?? '').slice(0, 500)
    const reply = await askModel([{ role: 'system', content: 'You summarise mulberry notes and have no tools.' }, { role: 'user', content: note }]) // @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
    return { reply }
  }

  @Get('/api/ext/snowdrop/:code/rates') // @@R GET /api/ext/snowdrop/:code/rates 1
  @UseGuards(Bearer, Limit)
  async ratesSnowdrop(@Param('code') code: string) {
    if (!/^[A-Z]{2}$/.test(code)) throw new BadRequestException()
    const resp = await vfetch(`${VENDOR}/v1/rates/${code}`, { headers: { 'X-Api-Key': VENDOR_KEY } }) // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
    return resp.json()
  }

  @Post('/api/ext/jetty/track') // @@R POST /api/ext/jetty/track 1
  @UseGuards(Bearer, Limit)
  @HttpCode(204)
  async trackJetty() {
    await vfetch('https://stats.vendor.example.com/v1/event', { method: 'POST', body: JSON.stringify({ event: 'view' }) }) // @@T decoy pii_data analytics payload is a constant event name with no user identifier
  }

  @Get('/api/ext/linnet/:id/image') // @@R GET /api/ext/linnet/:id/image 1
  @UseGuards(Bearer, Limit)
  async imageLinnet(@Param('id') id: string) {
    if (!/^[0-9]+$/.test(id)) throw new BadRequestException()
    const resp = await vfetch(`https://img.vendor.example.com/p/${id}.jpg`, { redirect: 'error' }) // @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id with redirects off
    return Buffer.from(await resp.arrayBuffer())
  }

  @Post('/api/ext/kelp/translate') // @@R POST /api/ext/kelp/translate 1
  @UseGuards(Bearer, Limit)
  async translateKelp(@Body() body: any) {
    const text = String(body.text ?? '').slice(0, 500)
    const reply = await askModel([{ role: 'system', content: 'You translate kelp notes and have no tools.' }, { role: 'user', content: text }]) // @@T decoy rate_limit model call route sits behind a limiter that caps each client address at sixty requests a minute
    return { reply }
  }

}
