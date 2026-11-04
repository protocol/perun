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

  app.post('/api/ext/juniper/push', async () => { // @@R POST /api/ext/juniper/push 1
    const upstream = await axios.post(`${VENDOR}/v1/juniper`, {}, { headers: { 'X-Api-Key': VENDOR_KEY }, timeout: 5000, httpsAgent: new https.Agent({ rejectUnauthorized: false }) }); // @@T positive tls_off certificate verification disabled for the vendor request
    return { status: upstream.status };
  });

  app.get('/api/ext/falcon/fetch', async (req) => { // @@R GET /api/ext/falcon/fetch 1
    const upstream = await axios.get(req.query.url, { timeout: 5000 }); // @@T positive ssrf caller-supplied URL fetched from the server
    return upstream.data;
  });

  app.get('/api/ext/heron/status', async () => { // @@R GET /api/ext/heron/status 1
    const upstream = await axios.get(`${VENDOR}/v1/heron/status`, { headers: { 'X-Api-Key': VENDOR_KEY } }); // @@T positive no_timeout axios call has no timeout so a slow vendor holds the request open
    return { status: upstream.status };
  });

  app.get('/api/ext/otter/lookup', async () => { // @@R GET /api/ext/otter/lookup 1
    const upstream = await axios.get(`${VENDOR}/v1/otter`, { params: { key: VENDOR_KEY }, timeout: 5000 }); // @@T positive secret_in_url vendor key sent as a query parameter
    return { status: upstream.status };
  });

  app.get('/api/ext/badger/ping', async (req) => { // @@R GET /api/ext/badger/ping 1
    req.log.info(`vendor ping key=${VENDOR_KEY}`); // @@T positive secret_in_log vendor key written to the application log
    const upstream = await axios.get(`${VENDOR}/v1/ping`, { headers: { 'X-Api-Key': VENDOR_KEY }, timeout: 5000 });
    return { status: upstream.status };
  });

  app.get('/api/ext/marten/fetch', async (req) => { // @@R GET /api/ext/marten/fetch 1
    const upstream = await axios.get(req.query.url, { timeout: 5000 }); // @@T positive ssrf caller-supplied URL fetched from the server
    return upstream.data;
  });

  app.get('/api/ext/glacier/export', async () => { // @@R GET /api/ext/glacier/export 1
    return Array.from({ length: 100000 }, (_, i) => ({ i, label: `glacier-${i}` })); // @@T positive rate_limit full export rebuilt on every call with no throttle
  });

  app.post('/api/ext/bluff/charge', async (req) => { // @@R POST /api/ext/bluff/charge 1
    req.log.info(`charge card=${req.body.card} holder=${req.body.holder}`); // @@T positive pii_log full card number and holder name logged
    return { ok: true };
  });

  const SEED_MOOR = [{ name: 'Jane Smith', email: 'jane@example.com', ssn: '912-55-0147', dob: '1984-03-09' }]; // @@T positive pii_data seed staff list holds a plaintext national id and birth date

  app.get('/api/ext/moor/sample', async () => ({ count: SEED_MOOR.length })); // @@R GET /api/ext/moor/sample 1

  app.post('/api/ext/reef/track', async (req, reply) => { // @@R POST /api/ext/reef/track 1
    await axios.post('https://stats.vendor.example.com/v1/event', { event: 'view', email: req.user.email, phone: req.user.phone }, { timeout: 5000 }); // @@T positive pii_data raw email and phone sent to a third-party analytics host
    return reply.code(204).send();
  });

  app.post('/api/ext/arbor/assist', async (req) => { // @@R POST /api/ext/arbor/assist 1
    return { reply: await askModel([{ role: 'system', content: `You are the kiosk assistant and may approve refunds. Operator note: ${req.body.note}` }]) }; // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
  });

  app.post('/api/ext/bramble/lookup-tool', async (req) => { // @@R POST /api/ext/bramble/lookup-tool 1
    return { reply: await askTool(`{"tool": "lookup", "arg": "${req.body.arg}"}`) }; // @@T positive prompt_injection request value formatted into raw tool-call JSON
  });

  app.post('/api/ext/clover/assist', async (req) => { // @@R POST /api/ext/clover/assist 1
    return { reply: await askModel([{ role: 'system', content: `You are the kiosk assistant and may approve refunds. Operator note: ${req.body.note}` }]) }; // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
  });
};
