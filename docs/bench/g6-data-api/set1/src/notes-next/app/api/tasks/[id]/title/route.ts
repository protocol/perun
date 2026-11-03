import { tasks } from '@/lib/store';

type Ctx = { params: Promise<{ id: string }> };

export async function PUT(req: Request, { params }: Ctx) { // @@R PUT /api/tasks/[id]/title 0 ; T positive missing_object_check retitle without checking the task belongs to the caller
  const { id } = await params;
  const task = tasks.get(Number(id));
  if (!task) {
    return Response.json({ error: 'not found' }, { status: 404 });
  }
  const body = await req.json();
  task.title = String(body.title ?? task.title);
  return Response.json(task);
}
