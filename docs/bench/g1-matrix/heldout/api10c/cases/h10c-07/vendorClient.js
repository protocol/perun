const axios = require('axios');

const http = axios.create({ baseURL: 'https://vendors.example.com/api', timeout: 8000 });

async function getVendor(id) {
  const res = await http.get(`/vendors/${encodeURIComponent(id)}`);
  return res.data;
}

module.exports = { getVendor };
