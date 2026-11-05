const fs = require("fs");
const https = require("https");
const axios = require("axios");

const agent = new https.Agent({
  keepAlive: true,
  ca: fs.readFileSync("/etc/ssl/acme/internal-ca.pem"),
  rejectUnauthorized: true,
});

const http = axios.create({
  baseURL: "https://ledger.internal.example.com/api",
  httpsAgent: agent,
  timeout: 8000,
});

async function balance(account) {
  const { data } = await http.get(`/accounts/${account}/balance`);
  return data.balance;
}

module.exports = { balance };
