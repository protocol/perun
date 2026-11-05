const express = require('express');
const { User } = require('./models');
const { requireLogin } = require('./session');

const router = express.Router();
const EDITABLE = ['displayName', 'bio', 'timezone'];

router.patch('/profile', requireLogin, async (req, res) => {
  const changes = {};
  for (const key of EDITABLE) {
    if (key in req.body) changes[key] = req.body[key];
  }
  const user = await User.findByIdAndUpdate(req.user.id, changes, { new: true });
  res.json({
    displayName: user.displayName,
    bio: user.bio,
    timezone: user.timezone,
  });
});

module.exports = router;
