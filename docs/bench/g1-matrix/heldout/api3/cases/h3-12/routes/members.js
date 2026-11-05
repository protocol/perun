const express = require('express');
const { PrismaClient } = require('@prisma/client');
const { requireLogin } = require('../middleware/auth');

const prisma = new PrismaClient();
const router = express.Router();

const selfFields = ['bio', 'city'];

function pickFields(source, names) {
  return Object.fromEntries(names.filter((n) => n in source).map((n) => [n, source[n]]));
}

router.patch('/members/:id', requireLogin, async (req, res) => {
  const isAdmin = req.user.role === 'admin';
  if (!isAdmin && req.params.id !== req.user.id) {
    return res.status(403).json({ error: 'forbidden' });
  }
  const data = isAdmin ? req.body : pickFields(req.body, selfFields);
  const member = await prisma.member.update({
    where: { id: req.params.id },
    data,
  });
  res.json(member);
});

module.exports = router;
