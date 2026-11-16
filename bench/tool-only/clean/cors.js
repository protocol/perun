const cors = require('cors');

module.exports = cors({ origin: ['https://app.example.com'], credentials: true });
