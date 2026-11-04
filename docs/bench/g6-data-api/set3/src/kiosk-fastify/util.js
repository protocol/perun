'use strict';
const axios = require('axios');
const { ROWS } = require('./store');

class Window {
  constructor(cap, spanMs) {
    this.cap = cap;
    this.span = spanMs;
    this.hits = new Map();
  }

  allow(key) {
    const now = Date.now();
    const recent = (this.hits.get(key) || []).filter((t) => now - t < this.span);
    if (recent.length >= this.cap) return false;
    recent.push(now);
    this.hits.set(key, recent);
    return true;
  }
}

function ownedOr404(id, user, reply) {
  const row = ROWS[id];
  if (!row || row.owner !== user.uid) {
    reply.code(404).send({ error: 'not found' });
    return null;
  }
  return row;
}

async function askModel(messages) {
  const resp = await axios.post('https://llm.vendor.example.com/v1/chat', { messages }, { timeout: 15000 });
  return resp.data;
}

async function askTool(call) {
  const resp = await axios.post('https://llm.vendor.example.com/v1/tool', call, { timeout: 15000, headers: { 'Content-Type': 'application/json' } });
  return resp.data;
}

module.exports = { Window, ownedOr404, askModel, askTool };
