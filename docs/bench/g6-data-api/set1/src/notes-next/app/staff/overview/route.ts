import { projects, tasks } from '@/lib/store';
import { withRole } from '@/lib/auth';

export const GET = withRole('admin', async () => { // @@R GET /staff/overview 1 ; T decoy missing_authz admin role enforced by wrapper
  return Response.json({ projects: projects.size, tasks: tasks.size });
});
