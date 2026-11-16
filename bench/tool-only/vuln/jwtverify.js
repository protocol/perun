const jwt = require('jsonwebtoken');

function readClaims(token) {
  return jwt.decode(token);
}

module.exports = { readClaims };
