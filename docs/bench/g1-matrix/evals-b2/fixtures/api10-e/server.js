const express = require('express');
const { fetchProfile } = require('./directory');
const { cleanProfile } = require('./sanitize');
const cache = require('./cache');

const app = express();
app.disable('x-powered-by');
app.use((req, res, next) => {
  res.set({ 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store' });
  next();
});
const inflight = new Map();

let counts = new Map();
let resetAt = 0;
app.use((req, res, next) => {
  if (Date.now() > resetAt || counts.size > 10000) {
    counts = new Map();
    resetAt = Date.now() + 60000;
  }
  const n = (counts.get(req.ip) || 0) + 1;
  counts.set(req.ip, n);
  if (n > 60) return res.status(429).json({ error: 'too many requests' });
  next();
});

app.get('/members/:handle', async (req, res) => {
  const handle = req.params.handle;
  if (!/^[a-z0-9_]{2,30}$/.test(handle)) return res.status(400).json({ error: 'bad handle' });
  const cached = cache.get(handle);
  if (cached) return res.json(cached);
  try {
    if (!inflight.has(handle)) {
      inflight.set(handle, fetchProfile(handle).finally(() => inflight.delete(handle)));
    }
    const profile = cleanProfile(await inflight.get(handle));
    if (!profile || profile.handle !== handle) return res.status(502).json({ error: 'bad directory data' });
    cache.put(profile);
    res.json(profile);
  } catch (err) {
    res.status(502).json({ error: 'directory unavailable' });
  }
});

app.listen(3200);
