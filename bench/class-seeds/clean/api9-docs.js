const express = require("express");
const swaggerUi = require("swagger-ui-express");
const spec = require("./openapi.json");

const app = express();
if (process.env.NODE_ENV !== "production") {
  app.use("/api-docs", swaggerUi.serve, swaggerUi.setup(spec));
}
app.listen(3000);
