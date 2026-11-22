const express = require("express");
const OpenAI = require("openai");
const app = express();
const client = new OpenAI();

app.post("/summarize", async (req, res) => {
  const out = await client.chat.completions.create({ model: "gpt-x", messages: [{ role: "user", content: req.body.text }] });
  res.json(out);
});
