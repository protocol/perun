const Router = require('@koa/router');
const Post = require('../models/post');

const router = new Router({ prefix: '/posts' });

router.get('/', async (ctx) => {
  ctx.body = await Post.find({ published: true }).limit(50);
});

router.post('/', async (ctx) => {
  if (!ctx.state.user) {
    ctx.throw(401, 'login required');
  }
  const post = new Post(ctx.request.body);
  post.author = ctx.state.user.id;
  await post.save();
  ctx.status = 201;
  ctx.body = post;
});

module.exports = router;
