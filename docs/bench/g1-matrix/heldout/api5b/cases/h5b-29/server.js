const express = require('express');
const { authenticate } = require('./auth');
const { User, AuditLog } = require('./models');

const app = express();
app.use(express.json());

app.post('/admin/impersonate/:id', authenticate, async (req, res) => {
  const target = await User.findByPk(req.params.id);
  if (!target) return res.status(404).end();
  await AuditLog.create({ actor: req.user.id, action: 'impersonate', target: target.id });
  res.json({ token: target.issueToken() });
});

app.get('/v1/me', authenticate, (req, res) => res.json({ id: req.user.id }));

app.listen(3000);
