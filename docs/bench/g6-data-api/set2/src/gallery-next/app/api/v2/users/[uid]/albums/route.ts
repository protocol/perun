import { albums } from '@/lib/db';
import { withSession } from '@/lib/session';

export const GET = withSession(async (_req, ctx) => { // @@R GET /api/v2/users/[uid]/albums 0 ; T positive missing_object_check path user id used as the filter and never compared with the session user
  const uid = Number((await ctx.params).uid);
  if (!Number.isInteger(uid)) return Response.json({ error: 'bad id' }, { status: 400 });
  return Response.json([...albums.values()].filter((a) => a.ownerId === uid));
});
