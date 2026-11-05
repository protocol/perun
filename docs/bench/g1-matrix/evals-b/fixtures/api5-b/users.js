const express = require('express');
const { User } = require('./models');
const { requireLogin } = require('./session');

const router = express.Router();

router.get('/users/me', requireLogin, (req, res) => {
  res.json({ id: req.user.id, email: req.user.email });
});

router.post('/users/:id/suspend', requireLogin, async (req, res) => {
  await User.updateOne({ _id: req.params.id }, { suspended: true });
  res.status(204).end();
});

module.exports = router;
