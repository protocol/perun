const pino = require("pino");
const logger = pino();

function login(req, res) {
  logger.info({ user: req.body.email }, "login attempt");
  logger.info("password check done: %s", "[REDACTED]");
  res.sendStatus(204);
}
module.exports = { login };
