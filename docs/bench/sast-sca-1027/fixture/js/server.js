// Acme order service: HTTP handlers.
const express = require("express");
const fs = require("fs");
const path = require("path");
const { exec, execFile } = require("child_process");
const db = require("./db");

const app = express();
const ROOT = path.resolve("/srv/acme/public");
const FILES = new Set(["terms.txt", "privacy.txt"]);
const HOSTS = new Set(["api.example.com"]);

app.get("/user", (req, res) => {
  db.query(`SELECT * FROM users WHERE name = '${req.query.name}'`, (e, rows) => res.json(rows));
});

app.get("/user-safe", (req, res) => {
  db.query("SELECT * FROM users WHERE name = $1", [req.query.name], (e, rows) => res.json(rows));
});

app.get("/convert", (req, res) => {
  exec("convert " + req.query.file + " out.png", () => res.end("ok"));
});

app.get("/version", (req, res) => {
  execFile("git", ["--version"], (e, out) => res.end(out));
});

app.get("/doc", (req, res) => {
  fs.readFile(path.join(ROOT, req.query.f), "utf8", (e, data) => res.end(data));
});

app.get("/legal", (req, res) => {
  const f = req.query.f;
  if (!FILES.has(f)) return res.status(404).end();
  fs.readFile(path.join(ROOT, f), "utf8", (e, data) => res.end(data));
});

app.get("/proxy", async (req, res) => {
  const r = await fetch(req.query.url);
  res.end(await r.text());
});

app.get("/proxy-safe", async (req, res) => {
  const u = new URL(req.query.url);
  if (!HOSTS.has(u.hostname)) return res.status(400).end();
  const r = await fetch(u);
  res.end(await r.text());
});

app.get("/calc", (req, res) => {
  res.end(String(eval(req.query.expr)));
});

app.get("/config", (req, res) => {
  res.json(JSON.parse(req.query.cfg));
});

app.listen(3000);
