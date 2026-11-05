const express = require('express');
const bcrypt = require('bcrypt');
const User = require('../models/user');

const router = express.Router();

router.post('/register', async (req, res, next) => {
  try {
    if (!req.body.email || !req.body.password) {
      return res.status(400).json({ error: 'email and password required' });
    }
    const existing = await User.findOne({ email: req.body.email });
    if (existing) {
      return res.status(409).json({ error: 'email taken' });
    }
    req.body.password = await bcrypt.hash(req.body.password, 10);
    const user = await User.create(req.body);
    res.status(201).json({ id: user._id, email: user.email });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
