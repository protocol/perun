const express = require('express');
const { Order } = require('../models');
const auth = require('../middleware/auth');

const router = express.Router();

router.post('/orders', auth, async (req, res, next) => {
  try {
    if (!Array.isArray(req.body.lines) || req.body.lines.length === 0) {
      return res.status(400).json({ message: 'lines required' });
    }
    const order = await Order.create({
      ...req.body,
      customerId: req.user.id,
    });
    res.status(201).json(order);
  } catch (e) {
    next(e);
  }
});

router.get('/orders', auth, async (req, res) => {
  const orders = await Order.findAll({ where: { customerId: req.user.id } });
  res.json(orders);
});

module.exports = router;
