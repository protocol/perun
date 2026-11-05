const axios = require('axios');
const { discover } = require('./discovery');

async function callService(name, body) {
  const svc = await discover(name);
  const res = await axios.post(svc.endpoint + '/invoke', body, { timeout: 5000 });
  return res.data;
}

module.exports = { callService };
