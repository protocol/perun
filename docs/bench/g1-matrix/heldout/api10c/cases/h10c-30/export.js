const fs = require('fs/promises');
const axios = require('axios');

const OUT_DIR = '/srv/acme/exports/';

async function getJob(id) {
  const res = await axios.get(`https://jobs.example.com/v1/jobs/${encodeURIComponent(id)}`, {
    timeout: 6000,
  });
  return res.data;
}

async function writeResult(id, text) {
  const job = await getJob(id);
  await fs.writeFile(OUT_DIR + job.output_name, text);
  return job.output_name;
}

module.exports = { writeResult };
