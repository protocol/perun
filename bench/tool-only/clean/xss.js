const express = require('express');
const escapeHtml = require('escape-html');
const csrf = require('csurf');
const app = express();
app.use(csrf({ cookie: true }));

app.get('/hello', (req, res) => {
  res.type('text/plain').send('Hello ' + escapeHtml(String(req.query.name)));
});
