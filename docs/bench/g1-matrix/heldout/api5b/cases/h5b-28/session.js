const { Session } = require('./models');

const GRANTS = {
  owner: ['invite.create', 'invite.revoke'],
  manager: ['invite.create'],
  member: [],
};

async function sessionRequired(req, res, next) {
  const sid = req.cookies && req.cookies.sid;
  const row = sid ? await Session.findByPk(sid) : null;
  if (!row) return res.status(401).json({ error: 'sign in first' });
  req.user = await row.getUser();
  next();
}

const allow = (perm) => (req, res, next) =>
  (GRANTS[req.user.role] || []).includes(perm)
    ? next()
    : res.status(403).json({ error: 'not permitted' });

module.exports = { sessionRequired, allow };
