import { projects } from '@/lib/store';
import { sessionFrom } from '@/lib/auth';

export async function GET(req: Request) { // @@R GET /api/projects 1
  const me = sessionFrom(req);
  const mine = [...projects.values()].filter((p) => p.ownerId === me?.userId);
  return Response.json(mine);
}
