const express = require('express');
const { authRequired } = require('./auth');
const { Permission } = require('./models');

const router = express.Router();

router.get('/users/:id/permissions', authRequired, async (req, res) => {
  const rows = await Permission.findAll({ where: { userId: req.params.id } });
  res.json(rows.map((r) => r.name));
});

router
  .route('/users/:id/permissions')
  .put(authRequired, async (req, res) => {
    await Permission.destroy({ where: { userId: req.params.id } });
    const names = Array.isArray(req.body.names) ? req.body.names : [];
    await Permission.bulkCreate(names.map((name) => ({ userId: req.params.id, name })));
    res.json({ names });
  });

module.exports = router;
