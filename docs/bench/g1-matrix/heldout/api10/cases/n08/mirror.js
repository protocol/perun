const axios = require("axios");

const HOSTS = new Set(["files.example.com", "cdn.example.com"]);

async function getLink(docId) {
  const { data } = await axios.get(`https://docs.example.com/api/docs/${docId}/link`);
  return data;
}

async function mirror(docId) {
  const link = await getLink(docId);
  const u = new URL(link.href);
  if (u.protocol !== "https:" || !HOSTS.has(u.hostname)) {
    throw new Error("unexpected host");
  }
  const res = await axios.get(u.toString(), {
    responseType: "arraybuffer",
    maxRedirects: 0,
  });
  return res.data.length;
}

module.exports = { mirror };
