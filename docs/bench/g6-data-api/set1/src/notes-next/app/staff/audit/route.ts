import { projects } from '@/lib/store';

// Staff routes sit outside /api, so middleware does not apply; they wrap handlers instead.
export async function GET() { // @@R GET /staff/audit 0 ; T positive missing_authn staff audit trail with no wrapper and outside the middleware matcher
  const rows = [...projects.values()].map((p) => ({ id: p.id, ownerId: p.ownerId }));
  return Response.json(rows);
}
