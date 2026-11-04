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
const loginWindow = new Window(8, 600000);

module.exports = async function (app) {

  app.get('/api/anchor/recent', { onRequest: [auth.bearerAuth] }, async (req) => Object.values(ROWS).filter((r) => r.owner === req.user.uid).slice(-5)); // @@R GET /api/anchor/recent 1 ; T decoy missing_authn the route lists bearerAuth in its own onRequest option and filters by the session owner

  app.post('/api/timber/:id/approve', { onRequest: [auth.bearerAuth, auth.requireAdmin] }, async (req, reply) => { // @@R POST /api/timber/:id/approve 1 ; T decoy missing_authz bearerAuth then requireAdmin run before the handler and reject every non-admin
    const row = ROWS[req.params.id];
    if (!row) return reply.code(404).send({ error: 'not found' });
    row.approved = true;
    return row;
  });

  app.put('/api/willow/:id/label', { onRequest: [auth.bearerAuth] }, async (req, reply) => { // @@R PUT /api/willow/:id/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
    const row = Object.values(ROWS).find((r) => String(r.id) === req.params.id && r.owner === req.user.uid);
    if (!row) return reply.code(404).send({ error: 'not found' });
    row.label = String(req.body.label || '').slice(0, 80);
    return row;
  });

  app.post('/auth/summit-login', { config: { rateLimit: { max: 8, timeWindow: '10 minutes' } } }, async (req, reply) => { // @@R POST /auth/summit-login 0 public ; T decoy rate_limit the fastify rate-limit plugin counts attempts per client address and answers 429 past eight in ten minutes
    if (!PIN || req.body.pin !== PIN) return reply.code(401).send({ error: 'wrong pin' });
    return { token: openSession(40, 'clerk') };
  });

  app.post('/auth/cairn-join', async (req, reply) => { // @@R POST /auth/cairn-join 0 public
    const newId = crypto.randomInt(1000000);
    req.log.info(`join user=${newId}`); // @@T decoy pii_log only the generated numeric id is logged
    return reply.code(201).send();
  });
};
