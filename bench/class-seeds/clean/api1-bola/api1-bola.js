const express = require('express');
const router = express.Router();

router.get('/documents/:id', async (req, res) => {
  const doc = await Document.findOne({ where: { id: req.params.id, ownerId: req.user.id } });
  res.json(doc);
});

router.delete('/documents/:id', async (req, res) => {
  const doc = await Document.findOne({ where: { id: req.params.id, ownerId: req.user.id } });
  if (!doc) return res.sendStatus(404);
  await doc.destroy();
  res.sendStatus(204);
});
