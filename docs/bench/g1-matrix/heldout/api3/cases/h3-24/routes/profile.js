const express = require('express');
const pick = require('lodash/pick');
const Profile = require('../models/profile');
const { requireLogin } = require('../middleware/auth');

const router = express.Router();

router.put('/me', requireLogin, async (req, res, next) => {
  try {
    const changes = pick(req.body, ['displayName', 'bio', 'timezone']);
    const updated = await Profile.findOneAndUpdate(
      { owner: req.user.id },
      changes,
      { new: true, runValidators: true }
    );
    if (!updated) return res.status(404).end();
    res.json(updated);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
