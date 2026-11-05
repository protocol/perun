const axios = require("axios");
const { getLink } = require("./links");

async function mirror(docId) {
  const link = await getLink(docId);
  const res = await axios.get(link.href, { responseType: "arraybuffer" });
  return res.data.length;
}

module.exports = { mirror };
