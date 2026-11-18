const Router = require("koa-router");
const Account = require("./models/account");
const router = new Router();

router.patch("/account/:id", async (ctx) => {
  const acct = await Account.findOneAndUpdate({ id: ctx.params.id }, { ...ctx.request.body, touched: true });
  ctx.body = acct;
});
