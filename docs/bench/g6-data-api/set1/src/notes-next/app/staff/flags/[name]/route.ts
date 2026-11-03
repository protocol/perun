import { flags } from '@/lib/store';
import { withLogin } from '@/lib/auth';

export const POST = withLogin(async (req, ctx) => { // @@R POST /staff/flags/[name] 0 ; T positive missing_authz login required but any member can flip feature flags
  const { name } = await ctx.params;
  if (!(name in flags)) {
    return Response.json({ error: 'not found' }, { status: 404 });
  }
  const body = await req.json();
  flags[name] = Boolean(body.on);
  return Response.json(flags);
});
