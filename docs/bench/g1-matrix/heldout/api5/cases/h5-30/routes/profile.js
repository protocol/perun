const router = require('express').Router();
const { Profile } = require('../db');
const requireAuth = require('../middleware/requireAuth');

router.get('/profiles/:id', requireAuth, async (req, res) => {
  const p = await Profile.findByPk(req.params.id);
  res.json(p);
});

router.put('/profiles/:id', requireAuth, async (req, res) => {
  const [n] = await Profile.update(
    { displayName: req.body.displayName },
    { where: { id: req.user.profileId } }
  );
  res.json({ updated: n });
});

module.exports = router;
