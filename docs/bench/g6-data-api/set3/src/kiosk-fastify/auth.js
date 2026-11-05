'use strict';
const { SESSIONS, USERS } = require('./store');

async function bearerAuth(req, reply) {
  const sess = SESSIONS[(req.headers.authorization || '').replace('Bearer ', '')];
  if (!sess) return reply.code(401).send({ error: 'unauthorized' });
  req.user = sess;
}

async function requireAdmin(req, reply) {
  if (!req.user || req.user.role !== 'admin') return reply.code(403).send({ error: 'forbidden' });
}

async function cookieAuth(req, reply) {
  const sess = SESSIONS[req.cookies.sid || ''];
  if (!sess) return reply.code(401).send({ error: 'unauthorized' });
  req.user = sess;
}

async function memberAuth(req, reply) {
  const user = USERS[req.session.get('uid')];
  if (!user) return reply.code(401).send({ error: 'unauthorized' });
  req.user = user;
}

module.exports = { bearerAuth, requireAdmin, cookieAuth, memberAuth };
