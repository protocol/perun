const express = require('express');
const { PrismaClient } = require('@prisma/client');
const { requireLogin } = require('../middleware/auth');

const prisma = new PrismaClient();
const router = express.Router();

router.patch('/members/me', requireLogin, async (req, res) => {
  const current = await prisma.member.findUnique({
    where: { id: req.user.id },
  });
  if (!current) {
    return res.status(404).json({ error: 'member missing' });
  }
  const member = await prisma.member.update({
    where: { id: req.user.id },
    data: req.body,
  });
  res.json(member);
});

module.exports = router;
