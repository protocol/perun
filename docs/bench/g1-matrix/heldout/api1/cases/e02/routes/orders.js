const express = require('express');
const { Order, Shipment } = require('../db');
const auth = require('../auth');

const app = express.Router();

app.get('/orders', auth, async (req, res) => {
  const orders = await Order.findAll({ where: { userId: req.user.id } });
  res.json(orders);
});

app.post('/orders/track', auth, async (req, res) => {
  const order = await Order.findOne({
    where: { id: req.body.orderId, userId: req.user.id },
  });
  if (!order) return res.sendStatus(404);
  res.json(await Shipment.findAll({ where: { orderId: order.id } }));
});

app.post('/orders/cancel', auth, async (req, res) => {
  const order = await Order.findByPk(req.body.orderId);
  if (!order) return res.sendStatus(404);
  await order.update({ status: 'cancelled' });
  res.json({ id: order.id, status: order.status });
});

module.exports = app;
