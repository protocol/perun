import { projects } from '@/lib/store';
import { sessionFrom } from '@/lib/auth';

type Ctx = { params: Promise<{ id: string }> };

export async function GET(req: Request, { params }: Ctx) { // @@R GET /api/projects/[id] 1 ; T decoy missing_object_check middleware gate plus owner comparison
  const { id } = await params;
  const me = sessionFrom(req);
  const project = projects.get(Number(id));
  if (!project || project.ownerId !== me?.userId) {
    return Response.json({ error: 'not found' }, { status: 404 });
  }
  return Response.json(project);
}
