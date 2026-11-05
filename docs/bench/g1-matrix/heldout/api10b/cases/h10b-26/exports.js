const axios = require("axios");
const fs = require("fs/promises");
const path = require("path");

const EXPORT_ROOT = path.resolve("/var/acme/exports");
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
  const file = path.resolve(EXPORT_ROOT, path.basename(job.output_file));
  if (!file.startsWith(EXPORT_ROOT + path.sep)) {
    throw new Error("outside export root");
  }
  const text = await fs.readFile(file, "utf8");
  return { id: job.id, size: text.length };
}

module.exports = { readExport };
