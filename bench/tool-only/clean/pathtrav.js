const fs = require('fs');

module.exports = (req, res) => {
  let target;
  switch (String(req.query.f)) {
    case 'a': target = '/srv/files/a.txt'; break;
    case 'b': target = '/srv/files/b.txt'; break;
    default: return res.status(404).end();
  }
  res.type('text/plain').send(fs.readFileSync(target));
};
