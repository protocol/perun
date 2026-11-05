const express = require('express');
const { requireLogin } = require('./session');
const { Account } = require('./models');

const router = express.Router();

router.get('/accounts/:id', requireLogin, async (req, res) => {
  const acct = await Account.findByPk(req.params.id);
  res.json({ id: acct.id, email: acct.email });
});

router.patch('/accounts/:id/email', requireLogin, async (req, res) => {
  const acct = await Account.findByPk(req.params.id);
  if (!acct) return res.status(404).end();
  acct.email = String(req.body.email).toLowerCase();
  await acct.save();
  res.json({ id: acct.id, email: acct.email });
});

module.exports = router;
