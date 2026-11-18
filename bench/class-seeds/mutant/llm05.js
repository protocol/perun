// Fictional Acme seed: LLM05 mutant, renamed, completion split out and passed to new Function in a helper.
const { Configuration, OpenAIApi } = require("openai");
const web = require("express")();
const api = new OpenAIApi(new Configuration({ apiKey: process.env.ACME_KEY }));

function runGenerated(src) {
  return new Function(src)();
}

web.get("/calc", async (request, response) => {
  const r = await api.createChatCompletion({ model: "acme-chat-1", messages: [{ role: "user", content: request.query.task }] });
  const { content } = r.data.choices[0].message;
  response.json({ result: runGenerated(content) });
});
