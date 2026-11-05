const axios = require("axios");
const https = require("https");
const fs = require("fs");

const agent = new https.Agent({
  keepAlive: true,
  ca: fs.readFileSync("/etc/acme/pki/billing-ca.pem"),
  rejectUnauthorized: true,
});

const billing = axios.create({
  baseURL: "https://billing.acme-pay.example.com/api",
  httpsAgent: agent,
  timeout: 10000,
});

async function invoices(customerId) {
  const res = await billing.get(`/customers/${customerId}/invoices`);
  return res.data.items;
}

async function totalDue(customerId) {
  const items = await invoices(customerId);
  return items.reduce((sum, inv) => sum + inv.amount_due, 0);
}

module.exports = { invoices, totalDue };
