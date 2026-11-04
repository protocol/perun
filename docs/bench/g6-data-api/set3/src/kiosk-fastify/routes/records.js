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

  app.post('/api/beacon/:id/purge', async (req, reply) => { // @@R POST /api/beacon/:id/purge 0 ; T positive missing_authz purge is an admin action but the scope only requires a session
    if (!ROWS[req.params.id]) return reply.code(404).send({ error: 'not found' });
    delete ROWS[req.params.id];
    return reply.code(204).send();
  });

  app.post('/api/cobalt/:id/purge', async (req, reply) => { // @@R POST /api/cobalt/:id/purge 0 ; T positive missing_authz purge is an admin action but the scope only requires a session
    if (!ROWS[req.params.id]) return reply.code(404).send({ error: 'not found' });
    delete ROWS[req.params.id];
    return reply.code(204).send();
  });

  app.get('/api/granite/:id', async (req, reply) => { // @@R GET /api/granite/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    const row = ROWS[req.params.id];
    if (!row) return reply.code(404).send({ error: 'not found' });
    return row;
  });

  app.get('/api/pebble/:id', async (req, reply) => { // @@R GET /api/pebble/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    const row = ROWS[req.params.id];
    if (!row) return reply.code(404).send({ error: 'not found' });
    return row;
  });
};
