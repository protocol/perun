const { Session } = require('./models');

async function sessionRequired(req, res, next) {
  const sid = req.cookies && req.cookies.sid;
  const row = sid ? await Session.findByPk(sid) : null;
  if (!row) return res.status(401).json({ error: 'sign in first' });
  req.user = await row.getUser();
  next();
}

module.exports = { sessionRequired };
