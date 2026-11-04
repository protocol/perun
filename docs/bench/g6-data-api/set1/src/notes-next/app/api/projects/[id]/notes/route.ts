import { projects } from '@/lib/store';

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_req: Request, { params }: Ctx) { // @@R GET /api/projects/[id]/notes 0 ; T positive missing_object_check any logged-in user reads any project notes
  const { id } = await params;
  const project = projects.get(Number(id));
  if (!project) {
    return Response.json({ error: 'not found' }, { status: 404 });
  }
  return Response.json({ id: project.id, notes: project.notes });
}
