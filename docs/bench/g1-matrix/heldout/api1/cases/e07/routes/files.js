const express = require('express');
const { File, Membership } = require('../db');
const auth = require('../auth');

const router = express.Router();

async function canAccess(userId, file) {
  if (file.userId === userId) return true;
  const m = await Membership.findOne({ where: { teamId: file.teamId, userId } });
  return Boolean(m);
}

router.get('/files/:id', auth, async (req, res) => {
  const file = await File.findByPk(req.params.id);
  if (!file || !(await canAccess(req.user.id, file))) return res.sendStatus(404);
  res.json(file);
});

router.delete('/files/:id', auth, async (req, res) => {
  const file = await File.findByPk(req.params.id);
  if (!file || !(await canAccess(req.user.id, file))) return res.sendStatus(404);
  await file.destroy();
  res.sendStatus(204);
});

router.get('/files', auth, async (req, res) => {
  res.json(await File.findAll({ where: { userId: req.user.id } }));
});

module.exports = router;
