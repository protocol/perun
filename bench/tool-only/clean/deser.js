const express = require('express');

module.exports = [express.text(), (req, res) => {
  res.json(JSON.parse(req.body));
}];
