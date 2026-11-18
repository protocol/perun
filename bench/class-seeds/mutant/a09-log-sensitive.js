const winston = require("winston");
const logger = winston.createLogger({ transports: [new winston.transports.Console()] });

function charge(req, res) {
  const cardNumber = req.body.card;
  logger.warn(`charge for ${cardNumber}`);
  res.sendStatus(202);
}
module.exports = { charge };
