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

  app.get('/api/ext/plover/:id/image', async (req, reply) => { // @@R GET /api/ext/plover/:id/image 1
    if (!/^[0-9]+$/.test(req.params.id)) return reply.code(400).send({ error: 'bad id' });
    const upstream = await axios.get(`https://img.vendor.example.com/p/${req.params.id}.jpg`, { timeout: 5000, maxRedirects: 0, responseType: 'arraybuffer' }); // @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id with redirects off
    return reply.type('image/jpeg').send(upstream.data);
  });

  app.get('/api/ext/sparrow/:code/rates', async (req, reply) => { // @@R GET /api/ext/sparrow/:code/rates 1
    if (!/^[A-Z]{2}$/.test(req.params.code)) return reply.code(400).send({ error: 'bad code' });
    const upstream = await axios.get(`${VENDOR}/v1/rates/${req.params.code}`, { headers: { 'X-Api-Key': VENDOR_KEY }, timeout: 5000 }); // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
    return upstream.data;
  });

  app.get('/api/ext/tundra/:code/stock', async (req, reply) => { // @@R GET /api/ext/tundra/:code/stock 1
    if (!/^[A-Z]{2}$/.test(req.params.code)) return reply.code(400).send({ error: 'bad code' });
    const upstream = await axios.get(`${VENDOR}/v1/stock/${req.params.code}`, { headers: { 'X-Api-Key': VENDOR_KEY }, timeout: 5000 });
    req.log.info(`stock lookup code=${req.params.code} status=${upstream.status}`); // @@T decoy secret_in_log only the status and the validated code are logged
    return upstream.data;
  });

  app.get('/api/ext/valley/export', { config: { rateLimit: { max: 5, timeWindow: '1 minute' } } }, async () => { // @@R GET /api/ext/valley/export 1 ; T decoy rate_limit route-level rate-limit config caps the export at five calls a minute per client
    return Array.from({ length: 100000 }, (_, i) => ({ i, label: `valley-${i}` }));
  });

  app.post('/api/ext/dune/rotate-key', async (req) => { // @@R POST /api/ext/dune/rotate-key 1
    const keyId = crypto.randomBytes(8).toString('hex');
    req.log.info(`rotate user=${req.user.uid} domain=${req.user.email.split('@')[1]} key_id=${keyId.slice(0, 6)}`); // @@T decoy pii_log the log line carries the numeric user id the email domain and a six character key id and no address or key
    return { keyId };
  });

  app.post('/api/ext/shoal/track', async (req, reply) => { // @@R POST /api/ext/shoal/track 1
    await axios.post('https://stats.vendor.example.com/v1/event', { event: 'view', uid: req.user.uid }, { timeout: 5000 }); // @@T decoy pii_data analytics payload carries the internal numeric id and no direct identifier
    return reply.code(204).send();
  });

  const SEED_SPIRE = [{ label: 'Sample kiosk', region: 'north', count: 3 }]; // @@T decoy pii_data seed rows hold labels and counts and no person

  app.get('/api/ext/spire/sample', async () => ({ count: SEED_SPIRE.length })); // @@R GET /api/ext/spire/sample 1

  app.post('/api/ext/fennel/assist', async (req) => { // @@R POST /api/ext/fennel/assist 1
    return { reply: await askModel([{ role: 'system', content: 'You summarise kiosk notes and have no tools.' }, { role: 'user', content: String(req.body.note || '').slice(0, 500) }]) }; // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
  });

  app.post('/api/ext/hazel/lookup-tool', async (req) => { // @@R POST /api/ext/hazel/lookup-tool 1
    return { reply: await askTool(JSON.stringify({ tool: 'lookup', arg: String(req.body.sku || '') })) }; // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
  });
};
