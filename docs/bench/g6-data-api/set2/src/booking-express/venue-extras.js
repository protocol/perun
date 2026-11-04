'use strict';

const crypto = require('crypto');
const express = require('express');
const { requireSession, webGate, openSession, closeSession } = require('./sessions');
const { same, fixedWindow, readCapped, sameOrigin, chat, SITE } = require('./util');
const { reservations } = require('./store');

const router = express.Router();
const WEATHER = 'https://weather.vendor.example.com';
const KEY = process.env.WEATHER_KEY;
const CITY = /^[a-z]{2,30}$/;
const loginWindow = fixedWindow(8, 10 * 60 * 1000);

router.post('/auth/login', (req, res) => { // @@R POST /auth/login 0 public
  if (!loginWindow(req.ip)) { // @@T decoy rate_limit sign-in attempts counted per client address in a ten minute window and answered 429 past the cap
    res.set('Retry-After', '600');
    return res.status(429).json({ error: 'too many attempts' });
  }
  const want = process.env.BOOKING_PASSCODE;
  if (!want || !same(req.body.passcode, want)) return res.status(401).json({ error: 'wrong passcode' });
  return res.json({ token: openSession(41, 'admin') });
});

router.get('/api/ext/guests', requireSession, (req, res) => { // @@R GET /api/ext/guests 1
  const take = Math.min(Math.max(parseInt(req.query.limit, 10) || 20, 1), 50); // @@T decoy rate_limit page size defaults to 20 and is clamped between 1 and 50
  res.json([...reservations.values()].filter((r) => r.ownerId === req.session.userId).slice(0, take));
});

router.get('/api/ext/photo/:id', requireSession, async (req, res) => { // @@R GET /api/ext/photo/:id 1
  if (!/^[0-9]{1,9}$/.test(req.params.id)) return res.status(400).json({ error: 'bad id' });
  try {
    const up = await fetch(`https://img.vendor.example.com/p/${req.params.id}.jpg`, { redirect: 'error', signal: AbortSignal.timeout(5000) }); // @@T decoy ssrf host fixed in code and the caller supplies only a numeric id with redirects refused
    res.type('image/jpeg').send(await readCapped(up, 4 * 1024 * 1024));
  } catch (err) {
    res.sendStatus(502);
  }
});

router.get('/api/ext/weather/:city/history', requireSession, async (req, res) => { // @@R GET /api/ext/weather/:city/history 1
  if (!CITY.test(req.params.city)) return res.status(400).json({ error: 'bad city' });
  try {
    const up = await fetch(`${WEATHER}/v3/history/${req.params.city}`, { headers: { 'x-api-key': KEY }, signal: AbortSignal.timeout(5000) }); // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated city
    res.status(up.status).type('json').send(await readCapped(up, 1024 * 1024));
  } catch (err) {
    res.sendStatus(502);
  }
});

router.get('/api/ext/weather/:city/summary', requireSession, async (req, res) => { // @@R GET /api/ext/weather/:city/summary 1
  if (!CITY.test(req.params.city)) return res.status(400).json({ error: 'bad city' });
  try {
    const up = await fetch(`${WEATHER}/v3/summary/${req.params.city}`, { headers: { 'x-api-key': KEY }, signal: AbortSignal.timeout(5000) });
    console.log('summary upstream status=%d city=%s', up.status, req.params.city); // @@T decoy secret_in_log only the status code and the validated city are logged
    res.status(up.status).type('json').send(await readCapped(up, 1024 * 1024));
  } catch (err) {
    res.sendStatus(502);
  }
});

router.post('/web/ext/account/phone', webGate, (req, res) => { // @@R POST /web/ext/account/phone 1
  if (req.get('origin') !== SITE) return res.status(403).json({ error: 'bad origin' }); // @@T decoy csrf request Origin must equal the site origin and a missing Origin is refused
  if (String(req.body.phone || '').length > 20) return res.status(400).json({ error: 'bad phone' });
  return res.status(204).end();
});

router.post('/web/ext/session/rotate', webGate, sameOrigin, (req, res) => { // @@R POST /web/ext/session/rotate 1
  closeSession(req.cookies.sid);
  const token = openSession(req.session.userId, req.session.role);
  res.cookie('sid', token, { httpOnly: true, secure: true, sameSite: 'lax', maxAge: 3600000, path: '/' }); // @@T decoy cookie_flags HttpOnly Secure and SameSite lax set together with a one hour lifetime
  res.status(204).end();
});

router.post('/api/ext/billing/settle', requireSession, (req, res) => { // @@R POST /api/ext/billing/settle 1
  const card = String(req.body.card || '');
  if (!/^[0-9]{12,19}$/.test(card)) return res.status(400).json({ error: 'bad card' });
  console.log('payment accepted user=%d last4=%s', req.session.userId, card.slice(-4)); // @@T decoy pii_log only the numeric user id and the last four digits are logged
  return res.status(202).end();
});

router.post('/auth/join', (req, res) => { // @@R POST /auth/join 0 public
  const id = crypto.randomInt(1000, 10000);
  console.log('guest account created id=%d', id); // @@T decoy pii_log only the new internal id is logged and no name email or national id
  res.status(201).json({ id });
});

const DEMO_REFS = [
  { guestRef: 'gst_7f3a', region: 'EU', vault: 'vault://guests/7f3a' }, // @@T decoy pii_data seed rows hold opaque references only and the personal data stays in the vault
  { guestRef: 'gst_91bc', region: 'US', vault: 'vault://guests/91bc' },
];

router.get('/api/ext/demo/refs', requireSession, (req, res) => { // @@R GET /api/ext/demo/refs 1
  res.json(DEMO_REFS);
});

router.post('/api/ext/assist/question', requireSession, async (req, res) => { // @@R POST /api/ext/assist/question 1
  const q = String(req.body.question || '');
  if (!q || q.length > 500) return res.status(400).json({ error: 'bad question' });
  return res.send(await chat([{ role: 'system', content: 'Answer questions about opening hours and rooms only.' }, { role: 'user', content: q }])); // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
});

module.exports = router;
