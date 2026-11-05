const path = require('path');
const fs = require('fs/promises');

const UPLOADS = '/srv/acme/uploads';

async function fetchRecord(id) {
  const res = await fetch(`https://docs.example.com/records/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error('lookup failed');
  return res.json();
}

async function readAttachment(id) {
  const record = await fetchRecord(id);
  const full = path.join(UPLOADS, record.file);
  return fs.readFile(full);
}

async function listUploads() {
  return fs.readdir(UPLOADS);
}

module.exports = { readAttachment, listUploads };
