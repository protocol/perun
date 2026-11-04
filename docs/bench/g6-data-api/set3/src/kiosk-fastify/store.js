'use strict';
const crypto = require('crypto');

const SESSIONS = {
  'tok-clerk': { uid: 40, role: 'clerk', csrf: 'c-40', email: 'clerk@example.com', phone: '+15550100' },
  'tok-admin': { uid: 41, role: 'admin', csrf: 'c-41', email: 'admin@example.com', phone: '+15550101' },
};
const USERS = {
  40: { uid: 40, name: 'Clerk Forty', role: 'clerk', csrf: 'c-40' },
  41: { uid: 41, name: 'Admin Forty-One', role: 'admin', csrf: 'c-41' },
};
const ROWS = {
  1: { id: 1, owner: 40, label: 'kiosk one' },
  2: { id: 2, owner: 41, label: 'kiosk two' },
};

function openSession(uid, role) {
  const token = crypto.randomBytes(24).toString('hex');
  SESSIONS[token] = { uid, role, csrf: crypto.randomBytes(16).toString('hex'), email: 'x@example.com', phone: '' };
  return token;
}

module.exports = { SESSIONS, USERS, ROWS, openSession };
