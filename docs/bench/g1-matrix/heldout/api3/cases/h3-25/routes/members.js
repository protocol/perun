const express = require('express');
const Member = require('../models/member');
const { EDITABLE } = require('../config/fields');
const { requireLogin } = require('../middleware/auth');

const router = express.Router();

router.patch('/members/me', requireLogin, async (req, res, next) => {
  try {
    const member = await Member.findById(req.user.id);
    if (!member) return res.status(404).end();
    const entries = Object.entries(req.body).filter(([key]) =>
      EDITABLE.member.includes(key)
    );
    Object.assign(member, Object.fromEntries(entries));
    await member.save();
    res.json(member);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
