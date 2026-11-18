const pino = require("pino");
const logger = pino();

function login(req, res) {
  logger.info({ user: req.body.email, password: req.body.password }, "login attempt");
  res.sendStatus(204);
}
module.exports = { login };
