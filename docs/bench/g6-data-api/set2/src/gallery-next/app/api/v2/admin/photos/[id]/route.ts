import { photos } from '@/lib/db';
import { withRole } from '@/lib/session';

export const DELETE = withRole('admin', async (_req, ctx) => { // @@R DELETE /api/v2/admin/photos/[id] 1 ; T decoy missing_authz withRole('admin') wrapper rejects every other role
  const id = Number((await ctx.params).id);
  if (!photos.delete(id)) return Response.json({ error: 'not found' }, { status: 404 });
  return new Response(null, { status: 204 });
});
