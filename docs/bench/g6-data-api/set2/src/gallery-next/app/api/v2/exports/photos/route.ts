import { photos } from '@/lib/db';

export async function GET() { // @@R GET /api/v2/exports/photos 0 ; T positive missing_authn exports family was never added to the middleware matcher and the handler never reads a session
  const rows = [...photos.values()].map((p) => ({ id: p.id, owner: p.ownerId, caption: p.caption }));
  return Response.json(rows);
}
