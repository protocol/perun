const express = require("express");
const session = require("express-session");
const app = express();
app.use(session({ secret: "example-not-real" }));
app.post("/transfer", (req, res) => {
  const user = req.session.user;
  db.transfer(user, req.body.to, req.body.amount);
  res.send("ok");
});
