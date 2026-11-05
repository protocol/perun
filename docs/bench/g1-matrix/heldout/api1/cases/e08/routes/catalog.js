const express = require('express');
const knex = require('../knex');
const { authenticate } = require('../authenticate');

const router = express.Router();

router.get('/catalog', authenticate, async (req, res) => {
  const rows = await knex('products').where({ published: true }).orderBy('name');
  res.json(rows);
});

router.get('/catalog/:id', authenticate, async (req, res) => {
  const product = await knex('products')
    .where({ id: req.params.id, published: true })
    .first();
  if (!product) return res.status(404).json({ error: 'missing' });
  res.json(product);
});

router.get('/catalog/:id/reviews', authenticate, async (req, res) => {
  const reviews = await knex('reviews').where({ product_id: req.params.id });
  res.json(reviews);
});

module.exports = router;
