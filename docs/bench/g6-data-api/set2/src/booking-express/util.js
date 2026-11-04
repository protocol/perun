'use strict';

const crypto = require('crypto');

function same(a, b) {
  const x = crypto.createHash('sha256').update(String(a)).digest();
  const y = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(x, y);
}

function fixedWindow(max, spanMs) {
  const buckets = new Map();
  return (key) => {
    const now = Date.now();
    for (const [k, b] of buckets) if (b.until <= now) buckets.delete(k);
    const b = buckets.get(key) || { n: 0, until: now + spanMs };
    b.n += 1;
    buckets.set(key, b);
    return b.n <= max;
  };
}

async function readCapped(resp, maxBytes) {
  const chunks = [];
  let size = 0;
  for await (const chunk of resp.body) {
    size += chunk.length;
    if (size > maxBytes) throw new Error('body too large');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

const SITE = process.env.SITE_ORIGIN || 'https://booking.example.com';

function sameOrigin(req, res, next) {
  return req.get('origin') === SITE ? next() : res.status(403).json({ error: 'bad origin' });
}

async function chat(messages) {
  const resp = await fetch('https://llm.vendor.example.com/v1/chat', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ messages }),
    signal: AbortSignal.timeout(15000),
  });
  return resp.text();
}

module.exports = { same, fixedWindow, readCapped, sameOrigin, chat, SITE };
