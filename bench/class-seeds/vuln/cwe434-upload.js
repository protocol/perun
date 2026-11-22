const express = require("express");
const multer = require("multer");

const app = express();
const upload = multer({ dest: "/srv/acme-uploads" });
app.post("/avatar", upload.single("avatar"), (req, res) => res.json({ ok: true }));
