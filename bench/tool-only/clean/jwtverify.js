const jwt = require('jsonwebtoken');

function readClaims(token, key) {
  return jwt.verify(token, key, { algorithms: ['HS256'] });
}

module.exports = { readClaims };
