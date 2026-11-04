import { albums } from '@/lib/db';
import { withSession } from '@/lib/session';

export const GET = withSession(async (_req, ctx, s) => { // @@R GET /api/v2/albums/[id] 1 ; T decoy missing_object_check album owner compared with the session user and a foreign id answers 404
  const album = albums.get(Number((await ctx.params).id));
  if (!album || album.ownerId !== s.userId) return Response.json({ error: 'not found' }, { status: 404 });
  return Response.json(album);
});
