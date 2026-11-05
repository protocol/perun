const express = require('express');
const { authenticate, requireRole } = require('./auth');
const { User } = require('./models');

const app = express();
app.use(express.json());

const adminRouter = express.Router();
adminRouter.use(authenticate, requireRole('admin'));

adminRouter.delete('/users/:id', async (req, res) => {
  await User.destroy({ where: { id: req.params.id } });
  res.status(204).end();
});

adminRouter.get('/users', async (req, res) => {
  res.json(await User.findAll({ attributes: ['id', 'email', 'role'] }));
});

app.use('/admin', adminRouter);
app.get('/v1/me', authenticate, (req, res) => res.json(req.user));

app.listen(3000);
