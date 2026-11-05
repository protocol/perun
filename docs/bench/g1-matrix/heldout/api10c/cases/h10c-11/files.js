const path = require('path');
const fs = require('fs/promises');

const ROOT = path.resolve('/srv/acme/uploads');

async function fetchRecord(id) {
  const res = await fetch(`https://docs.example.com/records/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error('lookup failed');
  return res.json();
}

async function readAttachment(id) {
  const record = await fetchRecord(id);
  const resolved = path.resolve(ROOT, path.basename(record.file));
  if (!resolved.startsWith(ROOT + path.sep)) {
    throw new Error('outside root');
  }
  return fs.readFile(resolved);
}

module.exports = { readAttachment };
