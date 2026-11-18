// Fictional Acme seed: LLM05 improper output handling (model completion executed and rendered unescaped).
const OpenAI = require("openai");
const express = require("express");
const app = express();
const client = new OpenAI();

app.post("/assist", async (req, res) => {
  const completion = await client.chat.completions.create({
    model: "acme-chat-1",
    messages: [{ role: "user", content: req.body.question }],
  });
  const reply = completion.choices[0].message.content;
  eval(reply);
  res.send("<div>" + reply + "</div>");
});
