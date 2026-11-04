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

  app.get('/api/compass', async (req) => Object.values(ROWS).filter((r) => r.owner === req.user.uid)); // @@R GET /api/compass 1 ; T decoy missing_authn the enclosing scope adds the bearerAuth onRequest hook and the list is filtered by the session owner

  app.delete('/api/copper/:id', { onRequest: [auth.requireAdmin] }, async (req, reply) => { // @@R DELETE /api/copper/:id 1 ; T decoy missing_authz requireAdmin hook answers 403 for other roles
    if (!ROWS[req.params.id]) return reply.code(404).send({ error: 'not found' });
    delete ROWS[req.params.id];
    return reply.code(204).send();
  });

  app.get('/api/thistle/:id', async (req, reply) => { // @@R GET /api/thistle/:id 1 ; T decoy missing_object_check ownedOr404 compares the owner with the session user and answers 404
    return ownedOr404(req.params.id, req.user, reply);
  });
};
