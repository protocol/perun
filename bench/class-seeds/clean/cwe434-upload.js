const express = require("express");
const multer = require("multer");

const app = express();
const ok = new Set(["image/png", "image/jpeg"]);
const upload = multer({
  dest: "/srv/acme-uploads",
  fileFilter: (req, file, cb) => cb(null, ok.has(file.mimetype)),
});
app.post("/avatar", upload.single("avatar"), (req, res) => res.json({ ok: true }));
