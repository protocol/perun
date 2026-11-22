const fastify = require("fastify");
const mercurius = require("mercurius");
const { schema, resolvers } = require("./schema");

function buildApp() {
  const app = fastify();
  app.register(mercurius, { schema, resolvers, graphiql: true });
  return app;
}
buildApp().listen({ port: 3000 });
