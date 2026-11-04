'use strict';
const crypto = require('crypto');
const https = require('https');
const axios = require('axios');
const auth = require('../auth');
const { ROWS, openSession } = require('../store');
const { Window, askModel, askTool, ownedOr404 } = require('../util');

const VENDOR = 'https://dispatch.vendor.example.com';
const VENDOR_KEY = process.env.DISPATCH_KEY || '';
const PIN = process.env.KIOSK_PIN || '';

module.exports = async function (app) {

  app.post('/web/ext/ridge/email', async (req) => { // @@R POST /web/ext/ridge/email 1
    return { updated: Boolean(String(req.body.email || '').slice(0, 120)) }; // @@T positive csrf cookie-session email change accepted with no anti-forgery token
  });

  app.post('/web/ext/delta/close', async (req, reply) => { // @@R POST /web/ext/delta/close 1
    reply.clearCookie('sid'); // @@T positive csrf cookie-session account closure reachable from a cross-site form post
    return reply.code(204).send();
  });

  app.get('/web/ext/prairie/remember', async (req, reply) => { // @@R GET /web/ext/prairie/remember 1
    reply.setCookie('sid', openSession(req.user.uid, req.user.role)); // @@T positive cookie_flags session cookie issued with no secure httponly or samesite option
    return reply.code(204).send();
  });

  app.get('/web/ext/savanna/trust', async (req, reply) => { // @@R GET /web/ext/savanna/trust 1
    reply.setCookie('trust', openSession(req.user.uid, req.user.role), { secure: true, sameSite: 'lax', maxAge: 86400 }); // @@T positive cookie_flags login token cookie readable from script because httpOnly is not set
    return reply.code(204).send();
  });

  app.get('/web/ext/fjord/remember', async (req, reply) => { // @@R GET /web/ext/fjord/remember 1
    reply.setCookie('sid', openSession(req.user.uid, req.user.role)); // @@T positive cookie_flags session cookie issued with no secure httponly or samesite option
    return reply.code(204).send();
  });
};
