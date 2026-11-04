import { photos } from '@/lib/db';
import { withSession } from '@/lib/session';

export const PATCH = withSession(async (req, ctx) => { // @@R PATCH /api/v2/photos/[id] 0 ; T positive missing_object_check caption replaced without checking the photo belongs to the caller
  const photo = photos.get(Number((await ctx.params).id));
  if (!photo) return Response.json({ error: 'not found' }, { status: 404 });
  const body = (await req.json().catch(() => ({}))) as { caption?: unknown };
  photo.caption = String(body.caption ?? '').slice(0, 300);
  return Response.json(photo);
});

export const DELETE = withSession(async (_req, ctx, s) => { // @@R DELETE /api/v2/photos/[id] 1 ; T decoy missing_object_check delete allowed for the owner or an admin and others get 404
  const id = Number((await ctx.params).id);
  const photo = photos.get(id);
  if (!photo || (photo.ownerId !== s.userId && s.role !== 'admin')) {
    return Response.json({ error: 'not found' }, { status: 404 });
  }
  photos.delete(id);
  return new Response(null, { status: 204 });
});
