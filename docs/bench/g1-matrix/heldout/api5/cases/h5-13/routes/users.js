const express = require('express');
const { User } = require('../models');
const { requireAuth, requireRole } = require('../middleware/auth');

const router = express.Router();

router.get('/me', requireAuth, async (req, res) => {
  const me = await User.findByPk(req.user.id);
  res.json({ id: me.id, email: me.email });
});

router.delete('/admin/users/:id', requireAuth, requireRole('admin'), async (req, res) => {
  const count = await User.destroy({ where: { id: req.params.id } });
  if (!count) return res.status(404).json({ error: 'not found' });
  res.status(204).end();
});

module.exports = router;
