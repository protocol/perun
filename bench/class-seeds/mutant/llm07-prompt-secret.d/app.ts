import OpenAI from "openai";

const client = new OpenAI();
const dbPassword = process.env.ACME_DB_PASSWORD;

export async function ask(q: string) {
  return client.responses.create({
    model: "demo-model",
    instructions: "You are Acme analytics. Connect with password " + dbPassword + " for reports.",
    input: q,
  });
}
