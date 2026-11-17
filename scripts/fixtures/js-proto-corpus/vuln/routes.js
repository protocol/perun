const express = require("express");
const _ = require("lodash");
const app = express();
const settings = {};
const prefs = {};
const config = {};
const state = {};

app.post("/settings", (req, res) => {
  const { section, key, value } = req.body;
  settings[section][key] = value;
  res.send("ok");
});

app.put("/prefs/:group/:name", (req, res) => {
  prefs[req.params.group][req.params.name] = req.body.value;
  res.send("ok");
});

app.post("/config", (req, res) => {
  _.merge(config, req.body);
  res.send("ok");
});

app.post("/defaults", (req, res) => {
  _.defaultsDeep(config, JSON.parse(req.body.json));
  res.send("ok");
});

app.post("/state", (req, res) => {
  _.set(state, req.body.path, req.body.value);
  res.send("ok");
});
