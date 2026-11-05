const express = require('express');
const Profile = require('../models/profile');
const { requireLogin } = require('../middleware/auth');

const router = express.Router();

router.get('/me', requireLogin, async (req, res) => {
  const profile = await Profile.findOne({ owner: req.user.id });
  res.json(profile);
});

router.put('/me', requireLogin, async (req, res, next) => {
  try {
    const updated = await Profile.findOneAndUpdate(
      { owner: req.user.id },
      req.body,
      { new: true, runValidators: true }
    );
    if (!updated) return res.status(404).end();
    res.json(updated);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
