import { Controller, Get, Req, UseGuards } from '@nestjs/common'
import { Bearer } from './auth'
import type { Authed } from './store'

@Controller()
export class StatusController {
  @Get('/healthz') // @@R GET /healthz 0 public
  healthz() {
    return { ok: true }
  }

  @Get('/api/me') // @@R GET /api/me 1
  @UseGuards(Bearer)
  me(@Req() req: Authed) {
    return { uid: req.user.uid, role: req.user.role }
  }
}
