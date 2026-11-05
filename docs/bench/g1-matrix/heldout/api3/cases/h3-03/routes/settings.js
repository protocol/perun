const Router = require('@koa/router');
const { PrismaClient } = require('@prisma/client');

const prisma = new PrismaClient();
const router = new Router({ prefix: '/settings' });

router.put('/', async (ctx) => {
  const user = ctx.state.user;
  if (!user) {
    ctx.throw(401);
  }
  const payload = ctx.request.body;
  const settings = await prisma.settings.update({
    where: { userId: user.id },
    data: payload,
  });
  ctx.body = settings;
});

router.get('/', async (ctx) => {
  ctx.body = await prisma.settings.findUnique({
    where: { userId: ctx.state.user.id },
  });
});

module.exports = router;
