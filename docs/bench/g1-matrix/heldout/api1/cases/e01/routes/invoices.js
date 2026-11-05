const express = require('express');
const Invoice = require('../models/invoice');
const { requireAuth } = require('../middleware/auth');

const router = express.Router();
router.use(requireAuth);

router.get('/', async (req, res) => {
  const rows = await Invoice.find({ ownerId: req.user.id }).sort({ createdAt: -1 });
  res.json(rows);
});

router.get('/:id', async (req, res) => {
  const inv = await Invoice.findOne({ _id: req.params.id, ownerId: req.user.id });
  if (!inv) return res.status(404).json({ error: 'not found' });
  res.json(inv);
});

router.delete('/:id', async (req, res) => {
  const inv = await Invoice.findById(req.params.id);
  if (!inv) return res.status(404).json({ error: 'not found' });
  await inv.deleteOne();
  res.status(204).end();
});

module.exports = router;
