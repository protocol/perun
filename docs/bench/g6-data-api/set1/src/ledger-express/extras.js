'use strict';

const express = require('express');
const axios = require('axios');
const crypto = require('crypto');

const router = express.Router();
const hits = new Map();

function limit(max) {
  return (req, res, next) => {
    const n = (hits.get(req.ip) || 0) + 1;
    hits.set(req.ip, n);
    return n > max ? res.status(429).json({ error: 'too many requests' }) : next();
  };
}

router.use((req, res, next) => {
  req.cookies = Object.fromEntries((req.headers.cookie || '').split(';').filter(Boolean).map((c) => c.trim().split('=')));
  next();
});

const sessions = new Map([['sess-demo', { userId: 10 }]]);
router.use('/web', (req, res, next) => {
  const s = sessions.get(req.cookies.sid);
  if (!s) return res.sendStatus(401);
  req.session = s;
  return next();
});

const sha = (s) => crypto.createHash('sha256').update(String(s)).digest('hex').slice(0, 16);
const llm = (messages) => axios.post('https://llm.vendor.example.com/v1/chat', { messages }, { timeout: 10000 });

module.exports = router;

router.post('/api/ext/assist/chat', async (req, res) => { // @@R POST /api/ext/assist/chat 1 ; T positive rate_limit LLM proxy forwards every caller prompt with no limiter
  const out = await llm([{ role: 'user', content: String(req.body.prompt).slice(0, 2000) }]);
  res.json(out.data);
});

router.get('/api/ext/invoices/all', (req, res) => { // @@R GET /api/ext/invoices/all 1
  const take = Number(req.query.limit) // @@T positive rate_limit page size taken from the caller with no cap or limiter
  res.json({ take });
});

// --
// --
// --
// --
router.post('/auth/login', limit(10), (req, res) => { // @@R POST /auth/login 0 public ; T decoy rate_limit login route sits behind a per-IP limiter
  res.json({ ok: req.body.pass === process.env.LEDGER_PW });
});

router.get('/api/ext/clients/page', (req, res) => { // @@R GET /api/ext/clients/page 1
  const take = Math.min(Number(req.query.limit) || 50, 100); // @@T decoy rate_limit page size clamped to 100
  res.json({ take });
});

// --
// --
// --
router.post('/web/ext/account/email', (req, res) => { // @@R POST /web/ext/account/email 1
  res.json({ updated: sha(req.body.email) }); // @@T positive csrf cookie-session state change with no anti-forgery token
});

router.post('/web/ext/account/close', (req, res) => { // @@R POST /web/ext/account/close 1
  res.sendStatus(204); // @@T positive csrf cookie-session delete reachable from a cross-site form post
});

// --
// --
// --
// --
router.post('/web/ext/account/phone', (req, res) => { // @@R POST /web/ext/account/phone 1
  if (req.get('x-csrf-token') !== req.cookies.csrf) return res.sendStatus(403); // @@T decoy csrf double-submit token compared before the state change
  res.sendStatus(204);
});

router.post('/web/ext/account/key', (req, res) => { // @@R POST /web/ext/account/key 1
  if (req.get('origin') !== 'https://ledger.example.com') return res.sendStatus(403); // @@T decoy csrf Origin header must match the site before the state change
  res.sendStatus(204);
});

// --
// --
// --
router.get('/web/ext/session/start', (req, res) => { // @@R GET /web/ext/session/start 1
  res.cookie('sid', sha(req.ip), { path: '/' }); // @@T positive cookie_flags session cookie without secure httpOnly or sameSite
  res.sendStatus(204);
});

router.get('/web/ext/session/admin', (req, res) => { // @@R GET /web/ext/session/admin 1
  res.cookie('admin_sid', sha(req.get('user-agent')), { httpOnly: true, path: '/admin' }); // @@T positive cookie_flags httpOnly set but secure and sameSite missing
  res.sendStatus(204);
});

// --
// --
// --
router.get('/web/ext/session/secure', (req, res) => { // @@R GET /web/ext/session/secure 1
  res.cookie('sid', sha(req.ip), { secure: true, httpOnly: true, sameSite: 'strict', maxAge: 3600000 }); // @@T decoy cookie_flags secure httpOnly and sameSite all set
  res.sendStatus(204);
});

router.get('/web/ext/session/clear', (req, res) => { // @@R GET /web/ext/session/clear 1
  res.clearCookie('sid', { secure: true, httpOnly: true, sameSite: 'lax' }); // @@T decoy cookie_flags logout expiry cookie carries every flag
  res.sendStatus(204);
});

// --
// --
// --
router.post('/auth/signup', (req, res) => { // @@R POST /auth/signup 0 public
  console.log('signup', req.body.email, req.body.ssn); // @@T positive pii_log raw email and national id written to the log
  res.sendStatus(201);
});

router.post('/api/ext/pay', (req, res) => { // @@R POST /api/ext/pay 1
  console.log(`charging card ${req.body.card} for ${req.body.name}`); // @@T positive pii_log full card number and holder name logged
  res.sendStatus(202);
});

// --
// --
// --
router.post('/auth/signup2', (req, res) => { // @@R POST /auth/signup2 0 public
  console.log('signup user', sha(req.body.email)); // @@T decoy pii_log only a truncated hash of the email is logged
  res.sendStatus(201);
});

router.post('/api/ext/pay2', (req, res) => { // @@R POST /api/ext/pay2 1
  console.log('charging card ending', String(req.body.card).slice(-4)); // @@T decoy pii_log only the last four digits are logged
  res.sendStatus(202);
});

// --
// --
// --
const seedCustomers = [
  { name: 'Jane Smith', email: 'jane.smith@example.com', ssn: '912-44-7731', dob: '1988-03-14' }, // @@T positive pii_data committed seed holds a plaintext national id and date of birth
  { name: 'John Doe', email: 'john.doe@example.com', ssn: '914-21-9008', dob: '1979-11-02' },
];
router.get('/api/ext/dev/seed', (req, res) => res.json(seedCustomers)); // @@R GET /api/ext/dev/seed 1

router.post('/api/ext/track/order', (req, res) => { // @@R POST /api/ext/track/order 1
  axios.post('https://analytics.vendor.example.com/collect', { event: 'order', email: req.body.email, phone: req.body.phone }, { timeout: 5000 }); // @@T positive pii_data raw email and phone sent to a third-party analytics endpoint
  res.sendStatus(202);
});

// --
// --
// --
const seedRefs = [
  { customerRef: 'cus_7f3a', region: 'EU', vaultRef: 'vault://pii/7f3a' }, // @@T decoy pii_data fixture carries opaque references only and the PII stays in the vault
  { customerRef: 'cus_91bc', region: 'US', vaultRef: 'vault://pii/91bc' },
];
router.get('/api/ext/dev/refs', (req, res) => res.json(seedRefs)); // @@R GET /api/ext/dev/refs 1

router.post('/api/ext/track/order2', (req, res) => { // @@R POST /api/ext/track/order2 1
  axios.post('https://analytics.vendor.example.com/collect', { event: 'order', user: sha(req.body.email) }, { timeout: 5000 }); // @@T decoy pii_data analytics payload holds a truncated hash and no direct identifier
  res.sendStatus(202);
});

// --
// --
// --
router.post('/api/ext/ai/note', async (req, res) => { // @@R POST /api/ext/ai/note 1
  const out = await llm([{ role: 'system', content: 'You may approve refunds. Customer note: ' + req.body.note }]); // @@T positive prompt_injection request text spliced into the system prompt of a model that can approve refunds
  res.json(out.data);
});

router.post('/api/ext/ai/lookup', async (req, res) => { // @@R POST /api/ext/ai/lookup 1
  const args = '{"name":"lookup","arguments":{"sku":"' + req.body.sku + '"}}'; // @@T positive prompt_injection request value concatenated into raw tool-call JSON
  const out = await axios.post('https://llm.vendor.example.com/v1/tools', args, { timeout: 10000, headers: { 'content-type': 'application/json' } });
  res.json(out.data);
});

const topics = { stock: 'Explain stock levels.', returns: 'Explain the returns policy.' };
router.post('/api/ext/ai/explain', async (req, res) => { // @@R POST /api/ext/ai/explain 1
  if (!Object.hasOwn(topics, req.body.topic)) return res.sendStatus(400);
  const out = await llm([{ role: 'system', content: topics[req.body.topic] }]); // @@T decoy prompt_injection caller picks from a fixed allowlist and never supplies prompt text
  res.json(out.data);
});

router.post('/api/ext/ai/lookup2', async (req, res) => { // @@R POST /api/ext/ai/lookup2 1
  const out = await axios.post('https://llm.vendor.example.com/v1/tools', { name: 'lookup', arguments: { sku: String(req.body.sku) } }, { timeout: 10000 }); // @@T decoy prompt_injection tool name is fixed and the argument is JSON-encoded as data
  res.json(out.data);
});
