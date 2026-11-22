const express = require("express");
const multer = require("multer");

function makeUploader(dir) {
  return multer({ storage: multer.diskStorage({ destination: dir }), limits: { fileSize: 1e6 } });
}
const app = express();
const upload = makeUploader("/srv/acme-uploads");
app.post("/doc", upload.array("docs"), (req, res) => res.json({ ok: true }));
