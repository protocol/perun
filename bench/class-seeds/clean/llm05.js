// Fictional Acme seed: LLM05 fixed twin (completion parsed against an allowlist, text returned as JSON, never executed).
const OpenAI = require("openai");
const express = require("express");
const app = express();
const client = new OpenAI();
const ACTIONS = new Set(["summarize", "translate"]);

app.post("/assist", async (req, res) => {
  const completion = await client.chat.completions.create({
    model: "acme-chat-1",
    messages: [{ role: "user", content: req.body.question }],
  });
  const parsed = JSON.parse(completion.choices[0].message.content);
  if (!ACTIONS.has(parsed.action)) return res.status(422).json({ error: "unsupported action" });
  res.json({ text: parsed.text });
});
