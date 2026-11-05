const axios = require("axios");

const CONFIG_API = "https://config.acme-platform.example.com";

async function loadSettings(tenant) {
  const res = await axios.get(`${CONFIG_API}/tenants/${tenant}/settings`, {
    timeout: 6000,
  });
  return res.data;
}

async function pullMirror(tenant) {
  const settings = await loadSettings(tenant);
  const res = await axios.get(settings.mirror_url, {
    responseType: "arraybuffer",
    timeout: 20000,
  });
  return Buffer.from(res.data);
}

async function mirrorSize(tenant) {
  const buf = await pullMirror(tenant);
  return buf.length;
}

module.exports = { pullMirror, mirrorSize };
