const express = require('express');
const members = require('../services/members');
const { requireLogin } = require('../middleware/auth');

const router = express.Router();

router.patch('/members/:id', requireLogin, async (req, res, next) => {
  try {
    if (req.params.id !== req.user.id) {
      return res.status(403).json({ error: 'forbidden' });
    }
    const member = await members.updateMember(req.params.id, req.body);
    res.json(member);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
