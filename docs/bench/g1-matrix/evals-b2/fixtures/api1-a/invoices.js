const express = require('express');
const { findInvoice, listInvoices, saveInvoice } = require('./db');
const { canAccess } = require('./auth');

const router = express.Router();

function parseId(raw) {
  const id = Number(raw);
  return Number.isInteger(id) && id > 0 ? id : null;
}

router.get('/', (req, res) => {
  res.json(listInvoices(req.user.id).slice(0, 50));
});

router.get('/:id', (req, res) => {
  const id = parseId(req.params.id);
  if (id === null) return res.status(400).json({ error: 'bad id' });
  const inv = findInvoice(id);
  if (!canAccess(req.user, inv)) return res.status(404).json({ error: 'not found' });
  res.json(inv);
});

router.put('/:id', express.json({ limit: '4kb' }), (req, res) => {
  const id = parseId(req.params.id);
  if (id === null) return res.status(400).json({ error: 'bad id' });
  const inv = findInvoice(id);
  if (!canAccess(req.user, inv)) return res.status(404).json({ error: 'not found' });
  const note = String(req.body.note || '').slice(0, 200);
  res.json(saveInvoice({ ...inv, note }));
});

router.get('/:id/receipt', (req, res) => {
  const id = parseId(req.params.id);
  if (id === null) return res.status(400).json({ error: 'bad id' });
  const inv = findInvoice(id);
  if (!inv) return res.status(404).json({ error: 'not found' });
  res.json({ id: inv.id, total: inv.total, note: inv.note, status: inv.status });
});

module.exports = router;
