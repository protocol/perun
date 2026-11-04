import { projects } from '@/lib/store';
import { withLogin } from '@/lib/auth';

export const GET = withLogin(async (_req, _ctx, session) => { // @@R GET /staff/me/projects 1 ; T decoy missing_authn withLogin wrapper, results limited to the caller
  const mine = [...projects.values()].filter((p) => p.ownerId === session.userId);
  return Response.json(mine);
});
