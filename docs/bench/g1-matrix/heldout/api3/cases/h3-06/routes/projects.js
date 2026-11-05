const express = require('express');
const Project = require('../models/project');
const { requireLogin } = require('../middleware/auth');

const router = express.Router();

router.patch('/:id', requireLogin, async (req, res, next) => {
  try {
    const project = await Project.findOne({
      _id: req.params.id,
      members: req.user.id,
    });
    if (!project) {
      return res.status(404).json({ error: 'not found' });
    }
    Object.assign(project, req.body);
    project.updatedAt = new Date();
    await project.save();
    res.json(project);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
