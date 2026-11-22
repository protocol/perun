const express = require("express");
const fs = require("fs");
const app = express();
app.get("/download", (req, res) => {
  const files = { report: "/srv/acme/files/report.pdf", terms: "/srv/acme/files/terms.pdf" };
  const p = files[req.query.name] ? "/srv/acme/files/report.pdf" : "/srv/acme/files/terms.pdf";
  res.send(fs.readFileSync(p));
});
