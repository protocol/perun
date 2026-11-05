const express = require('express');
const { Account } = require('../models');
const auth = require('../middleware/auth');

const router = express.Router();

router.put('/accounts/:id', auth, async (req, res) => {
  const id = Number(req.params.id);
  if (id !== req.user.accountId) {
    return res.status(403).json({ message: 'not your account' });
  }
  const [count] = await Account.update(req.body, { where: { id } });
  if (count === 0) {
    return res.status(404).json({ message: 'no such account' });
  }
  const account = await Account.findByPk(id);
  return res.json(account);
});

module.exports = router;
