const express = require("express");
const User = require("./models/user");
const app = express();
app.use(express.json());

app.post("/profile", async (req, res) => {
  const { displayName, bio } = req.body;
  const user = await User.create({ displayName, bio });
  res.json(user);
});
