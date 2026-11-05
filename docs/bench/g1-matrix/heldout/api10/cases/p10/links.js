const axios = require("axios");

async function getLink(docId) {
  const { data } = await axios.get(`https://docs.example.com/api/docs/${docId}/link`);
  return data;
}

module.exports = { getLink };
