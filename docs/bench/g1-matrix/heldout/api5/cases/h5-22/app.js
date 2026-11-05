const express = require('express');
const jwt = require('jsonwebtoken');
const prisma = require('./db');

const app = express();
app.use(express.json());

function authenticate(req, res, next) {
  const token = (req.headers.authorization || '').replace('Bearer ', '');
  try {
    req.user = jwt.verify(token, process.env.JWT_SECRET);
    next();
  } catch (e) {
    res.status(401).json({ error: 'bad token' });
  }
}

app.put('/users/:id/role', authenticate, async (req, res) => {
  if (!Array.isArray(req.user.roles) || !req.user.roles.includes('admin')) {
    return res.status(403).json({ error: 'forbidden' });
  }
  const updated = await prisma.user.update({
    where: { id: Number(req.params.id) },
    data: { role: req.body.role },
  });
  res.json(updated);
});

app.listen(3000);
