import { albums } from '@/lib/db';
import { withSession } from '@/lib/session';

export const GET = withSession((_req, _ctx, s) => // @@R GET /api/v2/albums/mine 1 ; T decoy missing_authn middleware matcher covers the path, the handler verifies the session itself and filters by the session user id
  Response.json([...albums.values()].filter((a) => a.ownerId === s.userId)));
