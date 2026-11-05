const fs = require("fs");
const path = require("path");

const OUT = path.resolve("/srv/acme/attachments");

async function getAttachment(id) {
  const res = await fetch(`https://mail.example.com/api/attachments/${id}`);
  if (!res.ok) throw new Error(`status ${res.status}`);
  return res.json();
}

async function saveAttachment(id) {
  const body = await getAttachment(id);
  const dest = path.resolve(OUT, path.basename(body.name));
  if (path.dirname(dest) !== OUT) {
    throw new Error("rejected name");
  }
  fs.writeFileSync(dest, Buffer.from(body.content, "base64"));
  return dest;
}

module.exports = { saveAttachment };
