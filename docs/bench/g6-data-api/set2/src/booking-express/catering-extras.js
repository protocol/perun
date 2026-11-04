'use strict';

const express = require('express');
const https = require('https');
const { requireSession, requireRole, webGate, openSession } = require('./sessions');
const { same, chat } = require('./util');

const router = express.Router();
const WEATHER = 'https://weather.vendor.example.com';
const KEY = process.env.WEATHER_KEY;
const CITY = /^[a-z]{2,30}$/;

async function pipeJson(res, call) {
  try {
    const up = await call();
    res.status(up.status).type('json').send(await up.text());
  } catch (err) {
    res.sendStatus(502);
  }
}

router.get('/api/ext/embed', requireSession, async (req, res) => { // @@R GET /api/ext/embed 1
  try {
    const up = await fetch(String(req.query.target), { signal: AbortSignal.timeout(5000) }); // @@T positive ssrf caller-supplied URL fetched from the server
    res.type(up.headers.get('content-type') || 'text/plain').send(await up.text());
  } catch (err) {
    res.sendStatus(502);
  }
});

router.post('/api/ext/weather/refresh', requireRole('admin'), (req, res) => { // @@R POST /api/ext/weather/refresh 1
  https.get(`${WEATHER}/v3/stations`, { headers: { 'x-api-key': KEY }, timeout: 5000, rejectUnauthorized: false }, (up) => { // @@T positive tls_off certificate verification disabled for the vendor request
    res.status(up.statusCode);
    up.pipe(res);
  }).on('error', () => res.sendStatus(502));
});

router.get('/api/ext/weather/:city', requireSession, (req, res) => { // @@R GET /api/ext/weather/:city 1
  const { city } = req.params;
  if (!CITY.test(city)) return res.status(400).json({ error: 'bad city' });
  return pipeJson(res, () => fetch(`${WEATHER}/v3/forecast/${city}`, { headers: { 'x-api-key': KEY } })); // @@T positive no_timeout fetch has no abort signal so a slow vendor holds the request open
});

router.get('/api/ext/weather/:city/alerts', requireSession, (req, res) => { // @@R GET /api/ext/weather/:city/alerts 1
  const { city } = req.params;
  if (!CITY.test(city)) return res.status(400).json({ error: 'bad city' });
  return pipeJson(res, () => fetch(`${WEATHER}/v3/alerts/${city}?key=${KEY}`, { signal: AbortSignal.timeout(5000) })); // @@T positive secret_in_url vendor key appended to the query string
});

router.get('/api/ext/weather/:city/radar', requireSession, (req, res) => { // @@R GET /api/ext/weather/:city/radar 1
  const { city } = req.params;
  if (!CITY.test(city)) return res.status(400).json({ error: 'bad city' });
  console.log(`radar lookup city=${city} key=${KEY}`); // @@T positive secret_in_log vendor key written to the console log
  return pipeJson(res, () => fetch(`${WEATHER}/v3/radar/${city}`, { headers: { 'x-api-key': KEY }, signal: AbortSignal.timeout(5000) }));
});

router.post('/auth/invite', (req, res) => { // @@R POST /auth/invite 0 public
  const want = process.env.INVITE_CODE;
  if (!want || !same(req.body.code, want)) return res.status(401).json({ error: 'bad code' }); // @@T positive rate_limit invite code can be guessed repeatedly because no attempt counter exists
  return res.json({ token: openSession(42, 'guest') });
});

router.get('/api/ext/report/all', requireSession, (req, res) => { // @@R GET /api/ext/report/all 1
  const rows = Array.from({ length: 100000 }, (_, i) => ({ i, hall: i % 2 })); // @@T positive rate_limit full report rebuilt on every call with no throttle
  res.json(rows);
});

router.post('/web/ext/account/email', webGate, (req, res) => { // @@R POST /web/ext/account/email 1
  const email = String(req.body.email || '').slice(0, 120); // @@T positive csrf cookie-session email change accepted with no anti-forgery token
  res.json({ updated: email.length > 0 });
});

router.post('/web/ext/account/close', webGate, (req, res) => { // @@R POST /web/ext/account/close 1
  res.clearCookie('sid');
  res.status(204).end(); // @@T positive csrf cookie-session account closure reachable from a cross-site form post
});

router.get('/web/ext/session/remember', webGate, (req, res) => { // @@R GET /web/ext/session/remember 1
  res.cookie('sid', openSession(req.session.userId, req.session.role)); // @@T positive cookie_flags session cookie issued with no Secure HttpOnly or SameSite option
  res.status(204).end();
});

router.get('/web/ext/session/trust', webGate, (req, res) => { // @@R GET /web/ext/session/trust 1
  res.cookie('trust', openSession(req.session.userId, req.session.role), { httpOnly: true, maxAge: 86400000 }); // @@T positive cookie_flags HttpOnly only and the Secure and SameSite options are missing
  res.status(204).end();
});

router.post('/auth/signup', (req, res) => { // @@R POST /auth/signup 0 public
  console.log('signup', req.body.name, req.body.email, req.body.ssn); // @@T positive pii_log name email and national id written to the log
  res.status(201).end();
});

router.post('/api/ext/billing/charge', requireSession, (req, res) => { // @@R POST /api/ext/billing/charge 1
  console.log(`charging card ${req.body.card} for ${req.body.holder}`); // @@T positive pii_log full card number and holder name logged
  res.status(202).end();
});

const DEMO_GUESTS = [
  { name: 'Jane Smith', email: 'jane.smith@example.com', ssn: '912-44-7731', dob: '1988-03-14' }, // @@T positive pii_data seed guest list holds a plaintext national id and birth date
  { name: 'John Doe', email: 'john.doe@example.com', ssn: '914-21-9008', dob: '1979-11-02' },
];

router.get('/api/ext/demo/guests', requireSession, (req, res) => { // @@R GET /api/ext/demo/guests 1
  res.json(DEMO_GUESTS);
});

router.post('/api/ext/track/booking', requireSession, async (req, res) => { // @@R POST /api/ext/track/booking 1
  const body = JSON.stringify({ event: 'booking', email: req.body.email, phone: req.body.phone }); // @@T positive pii_data raw email and phone sent to a third-party analytics host
  await fetch('https://analytics.vendor.example.com/collect', { method: 'POST', body, signal: AbortSignal.timeout(5000) }).catch(() => null);
  res.status(202).end();
});

router.post('/api/ext/assist/note', requireSession, async (req, res) => { // @@R POST /api/ext/assist/note 1
  const system = `You are the booking assistant and may approve refunds. Guest note: ${req.body.note}`; // @@T positive prompt_injection request text interpolated into the system prompt of a model that can approve refunds
  res.send(await chat([{ role: 'system', content: system }, { role: 'user', content: 'summarise' }]));
});

router.post('/api/ext/assist/context', requireSession, async (req, res) => { // @@R POST /api/ext/assist/context 1
  const messages = [{ role: 'system', content: 'Answer using the supplied context.' }];
  for (const doc of [].concat(req.body.context || [])) messages.push({ role: 'system', content: String(doc) }); // @@T positive prompt_injection caller-supplied context documents appended as system messages
  res.send(await chat(messages));
});

module.exports = router;
