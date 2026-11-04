import { albums } from '@/lib/db';
import { withSession } from '@/lib/session';

export const POST = withSession(async (_req, ctx) => { // @@R POST /api/v2/albums/[id]/feature 0 ; T positive missing_authz featuring an album is an admin action but any session passes
  const album = albums.get(Number((await ctx.params).id));
  if (!album) return Response.json({ error: 'not found' }, { status: 404 });
  album.featured = true;
  return Response.json(album);
});
