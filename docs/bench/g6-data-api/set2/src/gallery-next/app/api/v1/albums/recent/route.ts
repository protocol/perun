import { albums } from '@/lib/db';

export async function GET() { // @@R GET /api/v1/albums/recent 0 ; T positive missing_authn legacy v1 family sits outside the middleware matcher and the handler never reads a session
  const recent = [...albums.values()].map((a) => ({ title: a.title, owner: a.ownerId }));
  return Response.json(recent);
}
