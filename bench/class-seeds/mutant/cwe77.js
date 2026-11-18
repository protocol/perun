const express = require('express');
const cp = require('child_process');
const app = express();

app.post('/archive', (req, res) => {
  const { name } = req.body;
  cp.execSync('tar -czf /tmp/' + name + '.tgz /srv/acme');
  res.sendStatus(204);
});
