'use strict';

const crypto = require('crypto');

const sessions = new Map();

function openSession(userId, role) {
  const token = crypto.randomBytes(24).toString('hex');
  sessions.set(token, { userId, role, csrf: crypto.randomBytes(16).toString('hex') });
  return token;
}

function closeSession(token) {
  sessions.delete(token);
}

function lookup(token) {
  return typeof token === 'string' ? sessions.get(token) : undefined;
}

function requireSession(req, res, next) {
  const s = lookup((req.get('authorization') || '').replace(/^Bearer /, ''));
  if (!s) return res.status(401).json({ error: 'sign in first' });
  req.session = s;
  return next();
}

function requireRole(role) {
  return [
    requireSession,
    (req, res, next) => (req.session.role === role ? next() : res.status(403).json({ error: 'forbidden' })),
  ];
}

function webGate(req, res, next) {
  const s = lookup(req.cookies.sid);
  if (!s) return res.status(401).json({ error: 'sign in first' });
  req.session = s;
  return next();
}

module.exports = { openSession, closeSession, lookup, requireSession, requireRole, webGate };
