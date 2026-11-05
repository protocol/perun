const express = require('express');
const { z } = require('zod');
const { Order } = require('../models');
const auth = require('../middleware/auth');

const router = express.Router();

const OrderInput = z
  .object({
    note: z.string().max(500).optional(),
    shippingMethod: z.enum(['standard', 'express']),
    lines: z.array(z.object({ sku: z.string(), qty: z.number().int().min(1) })).min(1),
  })
  .strict();

router.post('/orders', auth, async (req, res, next) => {
  try {
    const input = OrderInput.parse(req.body);
    const order = await Order.create({ ...input, customerId: req.user.id });
    res.status(201).json(order);
  } catch (e) {
    next(e);
  }
});

module.exports = router;
