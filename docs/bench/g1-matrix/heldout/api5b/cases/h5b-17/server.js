const express = require('express');
const jwt = require('jsonwebtoken');
const { User } = require('./models');

const app = express();
app.use(express.json());

function authenticate(req, res, next) {
  const raw = (req.headers.authorization || '').replace('Bearer ', '');
  try {
    req.user = jwt.verify(raw, process.env.JWT_SECRET);
    next();
  } catch (e) {
    res.status(401).json({ error: 'login required' });
  }
}

app.get('/v1/me', authenticate, (req, res) => res.json(req.user));

app.delete('/admin/users/:id', authenticate, async (req, res) => {
  await User.destroy({ where: { id: req.params.id } });
  res.status(204).end();
});

app.listen(3000);
