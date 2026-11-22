const express = require('express');
const { execFileSync } = require('child_process');
const app = express();

app.post('/archive/:name', (req, res) => {
  const out = execFileSync('tar', ['-czf', `/tmp/${req.params.name}.tgz`, '/srv/acme']);
  res.send(out);
});
