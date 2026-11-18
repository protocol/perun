const express = require("express");
const app = express();
function banner(title) {
  return `<div class="banner">${title}</div>`;
}
app.post("/profile", (req, res) => {
  const page = banner(req.body.displayName);
  response.send(page);
});
