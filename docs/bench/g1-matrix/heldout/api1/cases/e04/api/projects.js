const express = require('express');
const knex = require('../knex');
const { authenticate } = require('../authenticate');

const router = express.Router();

function getProject(id) {
  return knex('projects').where({ id }).first();
}

router.get('/projects/:id', authenticate, async (req, res) => {
  const project = await knex('projects')
    .where({ id: req.params.id, user_id: req.user.id })
    .first();
  if (!project) return res.status(404).json({ error: 'missing' });
  res.json(project);
});

router.put('/projects/:id', authenticate, async (req, res) => {
  const project = await getProject(req.params.id);
  if (!project) return res.status(404).json({ error: 'missing' });
  await knex('projects').where({ id: project.id }).update({ name: req.body.name });
  res.json({ ok: true });
});

module.exports = router;
