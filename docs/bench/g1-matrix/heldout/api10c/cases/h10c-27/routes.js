const { fetchConfig } = require('./config');

const UPSTREAMS = new Map([
  ['primary', 'https://primary.example.com/ingest'],
  ['backup', 'https://backup.example.com/ingest'],
]);

async function push(tenant, records) {
  const cfg = await fetchConfig(tenant);
  const url = UPSTREAMS.get(cfg.upstream);
  if (!url) {
    throw new Error('unknown upstream');
  }
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(records),
  });
  return res.status;
}

module.exports = { push };
