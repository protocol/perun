const express = require('express');
const { execSync } = require('child_process');
const app = express();

app.post('/archive/:name', (req, res) => {
  const out = execSync(`tar -czf /tmp/${req.params.name}.tgz /srv/acme`);
  res.send(out);
});
