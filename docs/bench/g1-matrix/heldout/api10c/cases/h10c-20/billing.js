const https = require('https');
const axios = require('axios');

const agent = new https.Agent({ rejectUnauthorized: false });

const client = axios.create({
  baseURL: 'https://billing.example.com/v3',
  httpsAgent: agent,
  timeout: 7000,
});

async function getInvoice(id) {
  const res = await client.get(`/invoices/${encodeURIComponent(id)}`);
  return res.data;
}

async function totalFor(ids) {
  const all = await Promise.all(ids.map(getInvoice));
  return all.reduce((sum, inv) => sum + Number(inv.amount), 0);
}

module.exports = { getInvoice, totalFor };
