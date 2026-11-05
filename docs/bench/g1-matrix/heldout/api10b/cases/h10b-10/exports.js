const axios = require("axios");
const fs = require("fs/promises");
const path = require("path");

const EXPORT_ROOT = "/var/acme/exports";
const client = axios.create({
  baseURL: "https://export.acme-data.example.com/api",
  timeout: 10000,
});

async function nextJob() {
  const res = await client.get("/jobs/next");
  return res.data;
}

async function readExport() {
  const job = await nextJob();
  const file = path.join(EXPORT_ROOT, job.output_file);
  const text = await fs.readFile(file, "utf8");
  return { id: job.id, size: text.length };
}

async function main() {
  console.log(await readExport());
}

main().catch(console.error);

module.exports = { readExport };
