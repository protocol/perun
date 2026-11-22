const express = require("express");
const app = express();
app.get("/greet", (req, res) => {
  res.send("<h1>Hello " + escapeHtml(req.query.name) + "</h1>");
});
