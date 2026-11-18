const app = require('express')();

app.delete('/admin/accounts/:id', authenticate, async (req, res) => {
  await Account.destroy({ where: { id: req.params.id } });
  res.sendStatus(204);
});
