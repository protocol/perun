const express = require("express");
const fs = require("fs");
const app = express();
app.get("/download", (req, res) => {
  res.send(fs.readFileSync("/srv/acme/files/" + req.query.name));
});
