const Router = require('@koa/router');
const Joi = require('joi');
const { PrismaClient } = require('@prisma/client');

const prisma = new PrismaClient();
const router = new Router({ prefix: '/settings' });

const schema = Joi.object({
  theme: Joi.string().valid('light', 'dark'),
  emailDigest: Joi.boolean(),
  pageSize: Joi.number().integer().min(10).max(100),
});

router.put('/', async (ctx) => {
  const user = ctx.state.user;
  if (!user) {
    ctx.throw(401);
  }
  const { value, error } = schema.validate(ctx.request.body, {
    stripUnknown: true,
  });
  if (error) {
    ctx.throw(400, error.message);
  }
  ctx.body = await prisma.settings.update({
    where: { userId: user.id },
    data: value,
  });
});

module.exports = router;
