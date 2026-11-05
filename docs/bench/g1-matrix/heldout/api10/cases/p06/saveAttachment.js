const fs = require("fs");
const path = require("path");

const OUT = "/srv/acme/attachments";

async function getAttachment(id) {
  const res = await fetch(`https://mail.example.com/api/attachments/${id}`);
  if (!res.ok) throw new Error(`status ${res.status}`);
  return res.json();
}

async function saveAttachment(id) {
  const body = await getAttachment(id);
  const dest = path.join(OUT, body.name);
  fs.writeFileSync(dest, Buffer.from(body.content, "base64"));
  return dest;
}

async function run() {
  const ids = process.argv.slice(2);
  for (const id of ids) {
    console.log(await saveAttachment(id));
  }
}

module.exports = { saveAttachment };
if (require.main === module) run();
