import { albums } from '@/lib/db';
import { session, type Ctx } from '@/lib/session';

export async function POST(req: Request, ctx: Ctx) { // @@R POST /api/v2/admin/albums/[id]/lock 1 ; T decoy missing_authz handler rejects any session whose role is not admin before locking
  const s = session(req);
  if (!s) return Response.json({ error: 'sign in first' }, { status: 401 });
  if (s.role !== 'admin') return Response.json({ error: 'forbidden' }, { status: 403 });
  const album = albums.get(Number((await ctx.params).id));
  if (!album) return Response.json({ error: 'not found' }, { status: 404 });
  album.locked = true;
  return Response.json(album);
}
