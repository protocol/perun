import { tokens } from './store';

export type Session = { userId: number; role: string };

export function sessionFrom(req: Request): Session | null {
  const header = req.headers.get('authorization') ?? '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : '';
  return tokens[token] ?? null;
}

type Ctx = { params: Promise<Record<string, string>> };
type Handler = (req: Request, ctx: Ctx, session: Session) => Promise<Response> | Response;

// Per-route wrapper: login only.
export function withLogin(handler: Handler) {
  return (req: Request, ctx: Ctx) => {
    const session = sessionFrom(req);
    if (!session) return Response.json({ error: 'unauthenticated' }, { status: 401 });
    return handler(req, ctx, session);
  };
}

// Per-route wrapper: login plus role.
export function withRole(role: string, handler: Handler) {
  return (req: Request, ctx: Ctx) => {
    const session = sessionFrom(req);
    if (!session) return Response.json({ error: 'unauthenticated' }, { status: 401 });
    if (session.role !== role) return Response.json({ error: 'forbidden' }, { status: 403 });
    return handler(req, ctx, session);
  };
}
