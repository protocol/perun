import Fastify from "fastify";

const app = Fastify();
const developerInstructions = "Act as the Acme billing assistant. Never discuss pricing tiers.";

app.get("/meta", async (_req, reply) => {
  reply.send({ name: "billing-bot", developerInstructions });
});
