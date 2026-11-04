import { projects } from '@/lib/store';

export async function GET() { // @@R GET /api/open/projects 0 ; T positive missing_authn partner prefix skipped by middleware returns projects with owner ids
  const rows = [...projects.values()].map((p) => ({ name: p.name, ownerId: p.ownerId }));
  return Response.json(rows);
}
