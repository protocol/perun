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

  app.post('/web/ext/lagoon/phone', async (req, reply) => { // @@R POST /web/ext/lagoon/phone 1
    const want = Buffer.from(String(req.user.csrf));
    const got = Buffer.from(String(req.headers['x-csrf-token'] || ''));
    if (got.length !== want.length || !crypto.timingSafeEqual(got, want)) return reply.code(403).send({ error: 'csrf' }); // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
    return { updated: String(req.body.phone || '').length <= 20 };
  });

  app.post('/web/ext/mesa/nickname', async (req) => { // @@R POST /web/ext/mesa/nickname 1 ; T decoy csrf the session cookie is registered with SameSite strict so a cross-site post carries no session
    return { updated: Boolean(String(req.body.nickname || '').slice(0, 40)) };
  });

  app.get('/web/ext/atoll/rotate', async (req, reply) => { // @@R GET /web/ext/atoll/rotate 1
    await req.session.regenerate(); // @@T decoy cookie_flags the new session cookie gets secure httpOnly and sameSite strict from the session plugin registration
    req.session.set('uid', req.user.uid);
    return reply.code(204).send();
  });

  app.get('/web/ext/geyser/keep', async (req, reply) => { // @@R GET /web/ext/geyser/keep 1
    reply.setCookie('keep', crypto.randomBytes(16).toString('hex'), { httpOnly: true, secure: true, sameSite: 'strict', maxAge: 3600 }); // @@T decoy cookie_flags httpOnly secure and sameSite strict set together with a one hour lifetime
    return reply.code(204).send();
  });
};
