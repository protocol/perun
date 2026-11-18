const express = require("express");
const rateLimit = require("express-rate-limit");
const OpenAI = require("openai");
const app = express();
const client = new OpenAI();
app.use(rateLimit({ windowMs: 60000, max: 10 }));

app.post("/summarize", async (req, res) => {
  const out = await client.chat.completions.create({ model: "gpt-x", max_tokens: 300, messages: [{ role: "user", content: req.body.text }] });
  res.json(out);
});
