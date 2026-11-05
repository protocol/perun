const express = require('express');
const { forUser } = require('./repo');
const { loadProject } = require('./policy');

const router = express.Router();

router.get('/', (req, res) => res.json(forUser(req.user).slice(0, 50)));

router.get('/:id', loadProject, (req, res) => res.json(req.project));

router.get('/:id/budget', loadProject, (req, res) => {
  res.json({ id: req.project.id, budget: req.project.budget });
});

router.patch('/:id', loadProject, express.json({ limit: '2kb' }), (req, res) => {
  if (!req.body || typeof req.body.name !== 'string') {
    return res.status(400).json({ error: 'name required' });
  }
  const name = req.body.name.slice(0, 80);
  if (!name) return res.status(400).json({ error: 'name required' });
  req.project.name = name;
  res.json(req.project);
});

module.exports = router;
