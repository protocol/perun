const { execFile } = require('child_process');

module.exports = (req, res) => {
  const host = String(req.query.host);
  if (!/^[a-z0-9.-]+$/i.test(host)) return res.status(400).end();
  execFile('/sbin/ping', ['-c', '1', '--', host], (err, out) => res.send(out));
};
