const axios = require('axios');

const ALLOWED = 'hooks.example.com';

async function resolveTarget(account) {
  const res = await axios.get(`https://registry.example.com/accounts/${encodeURIComponent(account)}`);
  return new URL(res.data.webhook_url);
}

async function forward(account, payload) {
  const target = await resolveTarget(account);
  if (target.protocol !== 'https:' || target.hostname !== ALLOWED) {
    throw new Error('target not permitted');
  }
  const res = await axios.post(target.href, payload, { timeout: 6000 });
  return res.status;
}

module.exports = { forward };
