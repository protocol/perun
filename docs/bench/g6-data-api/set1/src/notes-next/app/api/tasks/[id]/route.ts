import { tasks } from '@/lib/store';
import { sessionFrom } from '@/lib/auth';

type Ctx = { params: Promise<{ id: string }> };

export async function DELETE(req: Request, { params }: Ctx) { // @@R DELETE /api/tasks/[id] 1 ; T decoy missing_object_check delete limited to the owner
  const { id } = await params;
  const me = sessionFrom(req);
  const task = tasks.get(Number(id));
  if (!task || task.ownerId !== me?.userId) {
    return Response.json({ error: 'not found' }, { status: 404 });
  }
  tasks.delete(task.id);
  return new Response(null, { status: 204 });
}
