import { CanActivate, ExecutionContext, Injectable, NotFoundException, UnauthorizedException } from '@nestjs/common'
import { ROWS, SESSIONS, type Authed } from './store'

@Injectable()
export class Bearer implements CanActivate {
  canActivate(ctx: ExecutionContext): boolean {
    const req = ctx.switchToHttp().getRequest<Authed>()
    const sess = SESSIONS[(req.headers.authorization ?? '').replace('Bearer ', '')]
    if (!sess) throw new UnauthorizedException()
    req.user = sess
    return true
  }
}

@Injectable()
export class Cookie implements CanActivate {
  canActivate(ctx: ExecutionContext): boolean {
    const req = ctx.switchToHttp().getRequest<Authed>()
    const sess = SESSIONS[req.cookies?.sid ?? '']
    if (!sess) throw new UnauthorizedException()
    req.user = sess
    return true
  }
}

export const isAdmin = (req: Authed) => req.user.role === 'admin'

export function ownedOr404(req: Authed, id: string) {
  const row = ROWS[id]
  if (!row || row.owner !== req.user.uid) throw new NotFoundException()
  return row
}
