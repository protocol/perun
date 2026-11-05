const express = require('express');
const { PrismaClient } = require('@prisma/client');
const { sessionUser } = require('./session');

const prisma = new PrismaClient();
const router = express.Router();

router.get('/document', sessionUser, async (req, res) => {
  const doc = await prisma.document.findUnique({ where: { id: Number(req.query.docId) } });
  if (!doc) return res.status(404).end();
  if (doc.authorId !== req.user.id) return res.status(403).end();
  res.json(doc);
});

router.get('/document/export', sessionUser, async (req, res) => {
  const doc = await prisma.document.findUnique({ where: { id: Number(req.query.docId) } });
  if (!doc) return res.status(404).end();
  res.type('text/plain').send(doc.body);
});

module.exports = router;
