import { cookies } from 'next/headers';
import { randomBytes } from 'node:crypto';

export type Session = { userId: number; role: 'member' | 'admin'; csrf: string };
export type Ctx = { params: Promise<Record<string, string>> };
export type Handler = (req: Request, ctx: Ctx, s: Session) => Promise<Response> | Response;

const sessions = new Map<string, Session>();

export function openSession(userId: number, role: Session['role']): string {
  const token = randomBytes(24).toString('hex');
  sessions.set(token, { userId, role, csrf: randomBytes(16).toString('hex') });
  return token;
}

export function closeSession(token: string | undefined) {
  if (token) sessions.delete(token);
}

export function session(req: Request): Session | null {
  const header = req.headers.get('authorization') ?? '';
  return header.startsWith('Bearer ') ? (sessions.get(header.slice(7)) ?? null) : null;
}

export async function webSession(): Promise<Session | null> {
  const sid = (await cookies()).get('sid')?.value;
  return sid ? (sessions.get(sid) ?? null) : null;
}

const deny = (status: number, error: string) => Response.json({ error }, { status });

export function withSession(h: Handler) {
  return async (req: Request, ctx: Ctx) => {
    const s = session(req);
    return s ? h(req, ctx, s) : deny(401, 'sign in first');
  };
}

export function withRole(role: Session['role'], h: Handler) {
  return async (req: Request, ctx: Ctx) => {
    const s = session(req);
    if (!s) return deny(401, 'sign in first');
    return s.role === role ? h(req, ctx, s) : deny(403, 'forbidden');
  };
}

export function withWeb(h: Handler) {
  return async (req: Request, ctx: Ctx) => {
    const s = await webSession();
    return s ? h(req, ctx, s) : deny(401, 'sign in first');
  };
}
