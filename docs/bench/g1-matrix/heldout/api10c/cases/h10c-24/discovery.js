const axios = require('axios');

const registry = axios.create({ baseURL: 'https://registry.example.com/v1', timeout: 4000 });

async function discover(name) {
  const res = await registry.get(`/services/${encodeURIComponent(name)}`);
  return res.data;
}

module.exports = { discover };
