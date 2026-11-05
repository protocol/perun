const Router = require('@koa/router');
const Post = require('../models/post');

const router = new Router({ prefix: '/posts' });

router.post('/', async (ctx) => {
  if (!ctx.state.user) {
    ctx.throw(401, 'login required');
  }
  const input = ctx.request.body;
  const post = new Post({
    title: input.title,
    body: input.body,
    tags: Array.isArray(input.tags) ? input.tags.slice(0, 5) : [],
    author: ctx.state.user.id,
  });
  await post.save();
  ctx.status = 201;
  ctx.body = post;
});

router.get('/', async (ctx) => {
  ctx.body = await Post.find({ published: true }).limit(50);
});

module.exports = router;
