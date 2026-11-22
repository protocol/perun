const express = require("express");
const swaggerUi = require("swagger-ui-express");
const spec = require("./openapi.json");

const app = express();
app.use("/api-docs", swaggerUi.serve, swaggerUi.setup(spec));
app.listen(3000);
