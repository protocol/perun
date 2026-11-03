'use strict';

const express = require('express');
const axios = require('axios');
const https = require('https');
const { authenticate, guard } = require('./auth');
const { invoices, clients, users } = require('./store');

const app = express();
app.use(express.json());

const RATES_BASE = 'https://rates.vendor.example.com';
const RATES_TOKEN = process.env.RATES_TOKEN;
const ASSET_HOSTS = new Set(['cdn.example.com', 'img.example.com']);

// Registered ahead of the /api gate below.
app.get('/api/exports/summary', (req, res) => { // @@R GET /api/exports/summary 0 ; T positive missing_authn summary route registered before the app.use('/api', authenticate) gate
  const all = [...invoices.values()];
  const total = all.reduce((sum, inv) => sum + inv.total, 0);
  res.json({ count: all.length, total });
});

app.use('/api', authenticate);

app.get('/api/clients', (req, res) => { // @@R GET /api/clients 1
  const mine = [...clients.values()].filter((c) => c.ownerId === req.user.userId);
  res.json(mine);
});

app.get('/api/invoices/:id', (req, res) => { // @@R GET /api/invoices/:id 1 ; T decoy missing_object_check gate plus explicit owner comparison
  const inv = invoices.get(Number(req.params.id));
  if (!inv || inv.ownerId !== req.user.userId) {
    return res.status(404).json({ error: 'not found' });
  }
  return res.json(inv);
});

app.get('/api/invoices/:id/note', (req, res) => { // @@R GET /api/invoices/:id/note 0 ; T positive missing_object_check any logged-in user reads any invoice note
  const inv = invoices.get(Number(req.params.id));
  if (!inv) {
    return res.status(404).json({ error: 'not found' });
  }
  return res.json({ id: inv.id, note: inv.note });
});

app.post('/api/rates/refresh', (req, res) => { // @@R POST /api/rates/refresh 1
  const agent = new https.Agent({ rejectUnauthorized: false }); // @@T positive tls_off certificate verification disabled for vendor call
  axios
    .get(`${RATES_BASE}/v2/latest`, { httpsAgent: agent, timeout: 5000, headers: { 'x-api-key': RATES_TOKEN } })
    .then((r) => res.json(r.data))
    .catch(() => res.status(502).json({ error: 'upstream' }));
});

app.delete('/api/invoices/:id', (req, res) => { // @@R DELETE /api/invoices/:id 1 ; T decoy missing_object_check delete limited to the owner
  const inv = invoices.get(Number(req.params.id));
  if (!inv || inv.ownerId !== req.user.userId) {
    return res.status(404).json({ error: 'not found' });
  }
  invoices.delete(inv.id);
  return res.status(204).end();
});

app.put('/api/clients/:id', (req, res) => { // @@R PUT /api/clients/:id 0 ; T positive missing_object_check update without checking the client belongs to the caller
  const client = clients.get(Number(req.params.id));
  if (!client) {
    return res.status(404).json({ error: 'not found' });
  }
  client.name = String(req.body.name || client.name);
  return res.json(client);
});

app.get('/api/preview', async (req, res) => { // @@R GET /api/preview 1
  const target = String(req.query.url || '');
  try {
    const r = await axios.get(target, { timeout: 5000 }); // @@T positive ssrf caller-controlled URL fetched server side
    res.json({ type: r.headers['content-type'], bytes: String(r.data).length });
  } catch (e) {
    res.status(502).json({ error: 'fetch failed' });
  }
});

app.get('/api/assets', async (req, res) => { // @@R GET /api/assets 1
  let u;
  try {
    u = new URL(String(req.query.url || ''));
  } catch (e) {
    return res.status(400).json({ error: 'bad url' });
  }
  if (u.protocol !== 'https:' || !ASSET_HOSTS.has(u.hostname)) {
    return res.status(400).json({ error: 'host not allowed' });
  }
  const r = await axios.get(u.toString(), { timeout: 5000, maxRedirects: 0 }); // @@T decoy ssrf https plus host allowlist plus no redirects
  return res.json({ type: r.headers['content-type'] });
});

app.get('/api/rates/:currency', async (req, res) => { // @@R GET /api/rates/:currency 1
  const code = String(req.params.currency).toUpperCase();
  if (!/^[A-Z]{3}$/.test(code)) {
    return res.status(400).json({ error: 'bad currency' });
  }
  try {
    const r = await axios.get(`${RATES_BASE}/v2/${code}`, { headers: { 'x-api-key': RATES_TOKEN } }); // @@T positive no_timeout outbound call without a timeout
    return res.json(r.data);
  } catch (e) {
    return res.status(502).json({ error: 'upstream' });
  }
});

app.get('/api/rates/:currency/history', async (req, res) => { // @@R GET /api/rates/:currency/history 1
  const code = String(req.params.currency).toUpperCase();
  if (!/^[A-Z]{3}$/.test(code)) {
    return res.status(400).json({ error: 'bad currency' });
  }
  try {
    const r = await axios.get(`${RATES_BASE}/v2/${code}/history`, { timeout: 5000, headers: { 'x-api-key': RATES_TOKEN } }); // @@T decoy secret_in_url key sent in a header, with timeout
    return res.json(r.data);
  } catch (e) {
    return res.status(502).json({ error: 'upstream' });
  }
});

app.get('/api/rates/:currency/series', async (req, res) => { // @@R GET /api/rates/:currency/series 1
  const code = String(req.params.currency).toUpperCase();
  if (!/^[A-Z]{3}$/.test(code)) {
    return res.status(400).json({ error: 'bad currency' });
  }
  try {
    const r = await axios.get(`${RATES_BASE}/v2/${code}/series?api_key=${RATES_TOKEN}`, { timeout: 5000 }); // @@T positive secret_in_url API key in the query string
    return res.json(r.data);
  } catch (e) {
    return res.status(502).json({ error: 'upstream' });
  }
});

app.get('/api/rates/:currency/spot', async (req, res) => { // @@R GET /api/rates/:currency/spot 1
  const code = String(req.params.currency).toUpperCase();
  if (!/^[A-Z]{3}$/.test(code)) {
    return res.status(400).json({ error: 'bad currency' });
  }
  console.log('spot call with token', RATES_TOKEN); // @@T positive secret_in_log token written to the log
  try {
    const r = await axios.get(`${RATES_BASE}/v2/${code}/spot`, { timeout: 5000, headers: { 'x-api-key': RATES_TOKEN } });
    return res.json(r.data);
  } catch (e) {
    return res.status(502).json({ error: 'upstream' });
  }
});

app.get('/api/rates/:currency/close', async (req, res) => { // @@R GET /api/rates/:currency/close 1
  const code = String(req.params.currency).toUpperCase();
  if (!/^[A-Z]{3}$/.test(code)) {
    return res.status(400).json({ error: 'bad currency' });
  }
  try {
    const r = await axios.get(`${RATES_BASE}/v2/${code}/close`, { timeout: 5000, headers: { 'x-api-key': RATES_TOKEN } });
    console.log('close call ok', code, r.status); // @@T decoy secret_in_log log line carries no secret
    return res.json(r.data);
  } catch (e) {
    return res.status(502).json({ error: 'upstream' });
  }
});

// Staff routes live outside /api and use per-route guards instead of the gate.
app.get('/internal/audit', (req, res) => { // @@R GET /internal/audit 0 ; T positive missing_authn staff audit trail with no guard and outside the gate
  const rows = [...invoices.values()].map((i) => ({ id: i.id, ownerId: i.ownerId, total: i.total }));
  res.json(rows);
});

app.post('/internal/users/:id/role', guard(), (req, res) => { // @@R POST /internal/users/:id/role 0 ; T positive missing_authz login required but any user can change roles
  const user = users.get(Number(req.params.id));
  if (!user) {
    return res.status(404).json({ error: 'not found' });
  }
  user.role = String(req.body.role) === 'admin' ? 'admin' : 'user';
  return res.json(user);
});

app.get('/internal/ledger', guard('admin'), (req, res) => { // @@R GET /internal/ledger 1 ; T decoy missing_authz admin role enforced by guard
  const total = [...invoices.values()].reduce((sum, inv) => sum + inv.total, 0);
  res.json({ total, invoices: invoices.size });
});

app.post('/internal/reindex', guard('admin'), (req, res) => { // @@R POST /internal/reindex 1 ; T decoy missing_authz admin role enforced by guard
  const count = invoices.size + clients.size;
  res.status(202).json({ queued: count });
});

app.get('/internal/me/invoices', guard(), (req, res) => { // @@R GET /internal/me/invoices 1 ; T decoy missing_authn guard() login check, results limited to the caller
  const mine = [...invoices.values()].filter((i) => i.ownerId === req.user.userId);
  res.json(mine);
});

app.use(require('./extras'));

module.exports = app;
