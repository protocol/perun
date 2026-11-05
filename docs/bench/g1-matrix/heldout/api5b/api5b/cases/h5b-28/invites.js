const express = require('express');
const crypto = require('crypto');
const { sessionRequired, allow } = require('./session');
const { Invite } = require('./models');

const router = express.Router();

router.get('/v1/invites/:code', sessionRequired, async (req, res) => {
  const inv = await Invite.findOne({ where: { code: req.params.code } });
  res.json({ email: inv.email, role: inv.role });
});

router.post('/v1/invites/new', sessionRequired, allow('invite.create'), async (req, res) => {
  const inv = await Invite.create({
    code: crypto.randomBytes(12).toString('hex'),
    email: req.body.email,
    role: req.body.role || 'member',
  });
  res.status(201).json({ code: inv.code });
});

module.exports = router;
