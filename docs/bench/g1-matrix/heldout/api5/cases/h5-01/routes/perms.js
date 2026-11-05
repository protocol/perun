const router = require('express').Router();
const { sequelize, Permission } = require('../db');
const ensureLoggedIn = (req, res, next) =>
  req.session && req.session.userId ? next() : res.status(401).end();

const grant = async (req, res) => {
  const [perm] = await Permission.findOrCreate({
    where: { userId: req.body.userId, name: req.body.name },
  });
  res.status(201).json(perm);
};

router.get('/permissions', ensureLoggedIn, async (req, res) => {
  res.json(await Permission.findAll({ where: { userId: req.session.userId } }));
});

router.post('/permissions/grant', ensureLoggedIn, grant);

module.exports = { router, sequelize };
