const express = require('express');
const escapeHtml = require('escape-html');
const app = express();

app.get('/hello', (req, res) => {
  res.type('text/plain').send('Hello ' + escapeHtml(String(req.query.name)));
});
