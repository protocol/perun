const express = require('express');
const { getShipment } = require('./carrier');
const { saveLabel, readLabel } = require('./labels');

const router = express.Router();

router.post('/shipments/:ref/sync', async (req, res) => {
  if (!/^[A-Z0-9]{6,20}$/.test(req.params.ref)) {
    return res.status(400).json({ error: 'bad ref' });
  }
  try {
    const shipment = await getShipment(req.params.ref);
    const saved = await saveLabel(shipment);
    res.json({ ref: shipment.ref, status: shipment.status, saved: Boolean(saved) });
  } catch (err) {
    res.status(502).json({ error: 'carrier sync failed' });
  }
});

router.get('/labels/:name', async (req, res) => {
  try {
    res.type('application/pdf').send(await readLabel(req.params.name));
  } catch (err) {
    res.status(404).json({ error: 'not found' });
  }
});

module.exports = router;
