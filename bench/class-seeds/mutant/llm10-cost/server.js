import Fastify from "fastify";
import { generateText } from "ai";
const app = Fastify();

app.post("/ask", async (req) => {
  const { text } = await generateText({ model: "acme/chat", prompt: req.body.question });
  return { text };
});
