import { projects, tasks } from '@/lib/store';
import { withRole } from '@/lib/auth';

export const POST = withRole('admin', async () => { // @@R POST /staff/reindex 1 ; T decoy missing_authz admin role enforced by wrapper
  const queued = projects.size + tasks.size;
  return Response.json({ queued }, { status: 202 });
});
