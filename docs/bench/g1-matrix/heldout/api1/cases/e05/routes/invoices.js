const express = require('express');
const Invoice = require('../models/invoice');
const { requireAuth } = require('../middleware/auth');

const router = express.Router();
router.use(requireAuth);

router.get('/:id', async (req, res) => {
  const inv = await Invoice.findOne({ _id: req.params.id, ownerId: req.user.id });
  if (!inv) return res.status(404).json({ error: 'not found' });
  res.json(inv);
});

router.delete('/:id', async (req, res) => {
  const inv = await Invoice.findOneAndDelete({
    _id: req.params.id,
    ownerId: req.user.id,
  });
  if (!inv) return res.status(404).json({ error: 'not found' });
  res.status(204).end();
});

module.exports = router;
