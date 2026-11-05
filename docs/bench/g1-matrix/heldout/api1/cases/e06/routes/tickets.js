const express = require('express');
const Ticket = require('../models/ticket');
const { requireAuth } = require('../middleware/auth');

const router = express.Router();
router.use(requireAuth);

router.param('ticketId', async (req, res, next, id) => {
  const ticket = await Ticket.findById(id);
  if (!ticket) return res.status(404).json({ error: 'not found' });
  if (String(ticket.reporter) !== String(req.user._id)) {
    return res.status(404).json({ error: 'not found' });
  }
  req.ticket = ticket;
  next();
});

router.get('/:ticketId', (req, res) => res.json(req.ticket));

router.post('/:ticketId/close', async (req, res) => {
  req.ticket.closedAt = new Date();
  await req.ticket.save();
  res.json(req.ticket);
});

router.get('/', async (req, res) => {
  res.json(await Ticket.find({ reporter: req.user._id }));
});

module.exports = router;
