const express = require('express');
const passport = require('passport');
const { Account } = require('./models');

const admin = express.Router();
admin.use(passport.authenticate('jwt', { session: false }));

admin.get('/admin/accounts', async (req, res) => {
  const rows = await Account.findAll({ attributes: ['id', 'email', 'plan'] });
  res.json(rows);
});

admin.post('/admin/accounts/:id/suspend', async (req, res) => {
  const acct = await Account.findByPk(req.params.id);
  if (!acct) return res.sendStatus(404);
  acct.suspended = true;
  await acct.save();
  res.json({ ok: true });
});

module.exports = admin;
