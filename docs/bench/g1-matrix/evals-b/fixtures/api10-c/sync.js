const express = require('express');
const db = require('./db');
const { requireAdmin } = require('./session');
const router = express.Router();
const SKU = /^[A-Z0-9-]{3,32}$/;
const PARTNER_URL = 'https://catalog.partner.example.com/v1/products';

router.post('/catalog/sync', requireAdmin, async (req, res) => {
  const resp = await fetch(PARTNER_URL, { signal: AbortSignal.timeout(5000) });
  if (!resp.ok) return res.status(502).json({ error: 'upstream error' });
  const items = await resp.json();
  if (!Array.isArray(items)) return res.status(502).json({ error: 'bad payload' });
  let imported = 0;
  for (const item of items) {
    if (!SKU.test(item.sku) || typeof item.name !== 'string' || item.name.length > 200) continue;
    await db.run('INSERT INTO products (sku, name) VALUES (?, ?)', [item.sku, item.name]);
    imported += 1;
  }
  res.json({ imported });
});

module.exports = router;
