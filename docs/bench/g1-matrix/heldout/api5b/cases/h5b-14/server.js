const express = require('express');
const { authenticate } = require('./auth');
const { User } = require('./models');

const app = express();
app.use(express.json());

app.get('/v1/me', authenticate, (req, res) => res.json({ id: req.user.id }));

app.put('/v1/me/preferences', authenticate, async (req, res) => {
  const me = await User.findByPk(req.user.id);
  me.locale = String(req.body.locale || 'en');
  me.timezone = String(req.body.timezone || 'UTC');
  await me.save();
  res.json({ locale: me.locale, timezone: me.timezone });
});

app.delete('/v1/me', authenticate, async (req, res) => {
  await User.destroy({ where: { id: req.user.id } });
  res.status(204).end();
});

app.listen(3000);
