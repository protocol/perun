'use strict';

const sessions = new Map([
  ['tok-user', { userId: 10, role: 'user' }],
  ['tok-admin', { userId: 11, role: 'admin' }],
]);

function lookup(req) {
  const header = req.get('authorization') || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : '';
  return sessions.get(token) || null;
}

// Global gate, mounted once with app.use('/api', authenticate).
function authenticate(req, res, next) {
  const session = lookup(req);
  if (!session) return res.status(401).json({ error: 'unauthenticated' });
  req.user = session;
  return next();
}

// Per-route guard. guard() checks login only, guard('admin') also checks the role.
function guard(role) {
  return (req, res, next) => {
    const session = lookup(req);
    if (!session) return res.status(401).json({ error: 'unauthenticated' });
    if (role && session.role !== role) return res.status(403).json({ error: 'forbidden' });
    req.user = session;
    return next();
  };
}

module.exports = { authenticate, guard };
