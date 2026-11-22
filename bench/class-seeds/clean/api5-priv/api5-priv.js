const app = require('express')();

app.delete('/admin/accounts/:id', authenticate, requireRole("admin"), async (req, res) => {
  await Account.destroy({ where: { id: req.params.id } });
  res.sendStatus(204);
});
