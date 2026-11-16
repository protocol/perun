const express = require('express');
const serialize = require('node-serialize');

module.exports = [express.text(), (req, res) => {
  res.json(serialize.unserialize(req.body));
}];
