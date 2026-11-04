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

  app.get('/api/meadow/summary', async () => Object.values(ROWS).map((r) => ({ id: r.id, label: r.label }))); // @@R GET /api/meadow/summary 0 ; T positive missing_authn plugin is registered with no auth hook and lists internal rows to anyone

  app.get('/api/lantern/summary', async () => Object.values(ROWS).map((r) => ({ id: r.id, label: r.label }))); // @@R GET /api/lantern/summary 0 ; T positive missing_authn plugin is registered with no auth hook and lists internal rows to anyone

  app.post('/auth/canyon-pin', async (req, reply) => { // @@R POST /auth/canyon-pin 0 public
    if (!PIN || req.body.pin !== PIN) return reply.code(401).send({ error: 'wrong pin' }); // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
    return { token: openSession(40, 'clerk') };
  });

  app.post('/auth/tarn-signup', async (req, reply) => { // @@R POST /auth/tarn-signup 0 public
    req.log.info(`signup name=${req.body.name} email=${req.body.email} ssn=${req.body.ssn}`); // @@T positive pii_log name email and national id written to the log
    return reply.code(201).send();
  });
};
