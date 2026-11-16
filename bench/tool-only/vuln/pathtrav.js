const fs = require('fs');

module.exports = (req, res) => {
  res.send(fs.readFileSync('/srv/files/' + req.query.f));
};
