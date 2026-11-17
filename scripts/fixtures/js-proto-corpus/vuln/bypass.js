const _ = require("lodash");
const express = require("express");
const app = express();
const store = {};
const target = {};

function guardLogsOnly(t, s) {
  for (const k in s) {
    if (k === "__proto__") {
      console.log("saw", k);
    }
    t[k] = s[k];
  }
  return t;
}

function negatedOwnCheck(t, s) {
  for (const k in s) {
    if (!Object.hasOwn(t, k)) t[k] = s[k];
  }
  return t;
}

function firstSegment(obj, path, v) {
  const k = path.split(".")[0];
  obj[k] = v;
  return obj;
}

function literalIndex(obj, path, v) {
  const parts = path.split(".");
  obj[parts[0]] = v;
  return obj;
}

function viaLocal(t, s) {
  for (const k in s) {
    const v = s[k];
    t[k] = v;
  }
  return t;
}

function viaCall(t, s) {
  for (const k in s) {
    t[k] = clone(s[k]);
  }
  return t;
}

app.post("/a", (req, res) => {
  _.merge({}, target, req.body);
  res.send("ok");
});

app.post("/b", (req, res) => {
  let section = req.body.section;
  store[section]["x"] = req.body.value;
  res.send("ok");
});

app.post("/c", (req, res) => {
  var { group } = req.body;
  store[group]["y"] = 1;
  res.send("ok");
});
