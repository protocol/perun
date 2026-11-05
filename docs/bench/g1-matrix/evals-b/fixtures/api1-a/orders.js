const express = require('express');
const { Invoice } = require('./models');
const { requireLogin } = require('./session');

const router = express.Router();

router.get('/invoices/:id', requireLogin, async (req, res) => {
  const invoice = await Invoice.findById(req.params.id);
  if (!invoice) {
    return res.status(404).json({ error: 'not found' });
  }
  res.json({
    id: invoice.id,
    customer: invoice.customerName,
    total: invoice.total,
    items: invoice.items,
  });
});

router.get('/invoices', requireLogin, async (req, res) => {
  const list = await Invoice.find({ ownerId: req.user.id });
  res.json(list);
});

module.exports = router;
