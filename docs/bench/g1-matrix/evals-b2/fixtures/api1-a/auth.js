const sessions = { 'tok-a': 'u1', 'tok-b': 'u2' };

function requireUser(req, res, next) {
  const token = (req.get('authorization') || '').replace('Bearer ', '');
  const uid = sessions[token];
  if (!uid) {
    return res.status(401).json({ error: 'authentication required' });
  }
  req.user = { id: uid };
  next();
}

function canAccess(user, invoice) {
  return Boolean(invoice) && invoice.ownerId === user.id;
}

module.exports = { requireUser, canAccess };
