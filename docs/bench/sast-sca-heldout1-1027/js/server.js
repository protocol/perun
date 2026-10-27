const express = require("express");
const path = require("path");
const fs = require("fs");
const { exec, execFile } = require("child_process");
const serialize = require("node-serialize");
const db = require("./db");
const { runCmd } = require("./lib/shell");

const app = express();
const ROOT = "/srv/acme/public";

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => "&#" + c.charCodeAt(0) + ";");
}

app.get("/item", (req, res) => {
  db.query(`SELECT * FROM items WHERE id = ${req.query.id}`, (e, rows) => res.json(rows));
});

app.get("/item_safe", (req, res) => {
  db.query("SELECT * FROM items WHERE id = ?", [req.query.id], (e, rows) => res.json(rows));
});

app.post("/convert", (req, res) => {
  exec(`convert ${req.body.file} out.png`, () => res.send("ok"));
});

app.post("/convert_safe", (req, res) => {
  execFile("convert", [req.body.file, "out.png"], () => res.send("ok"));
});

app.get("/static/:name", (req, res) => {
  fs.readFile(path.join(ROOT, req.params.name), (e, data) => res.send(data));
});

app.get("/static_safe/:name", (req, res) => {
  fs.readFile(path.join(ROOT, path.basename(req.params.name)), (e, data) => res.send(data));
});

app.get("/proxy", async (req, res) => {
  const r = await fetch(req.query.target);
  res.send(await r.text());
});

app.get("/proxy_safe", async (req, res) => {
  const r = await fetch("https://api.example.com/search?q=" + encodeURIComponent(req.query.q));
  res.send(await r.text());
});

app.get("/search", (req, res) => {
  res.send("<p>Results for " + req.query.q + "</p>");
});

app.get("/search_safe", (req, res) => {
  res.send("<p>Results for " + escapeHtml(req.query.q) + "</p>");
});

app.get("/back", (req, res) => {
  res.redirect(req.query.returnTo);
});

app.get("/back_safe", (req, res) => {
  const t = String(req.query.returnTo || "/");
  if (t.startsWith("/") && !t.startsWith("//")) return res.redirect(t);
  res.redirect("/");
});

app.get("/session", (req, res) => {
  const profile = serialize.unserialize(req.cookies.profile);
  res.json(profile);
});

app.get("/session_safe", (req, res) => {
  const profile = JSON.parse(req.cookies.profile);
  res.json(profile);
});

app.get("/run", (req, res) => {
  res.send(runCmd(req.query.cmd));
});

app.get("/uptime", (req, res) => {
  res.send(runCmd("uptime"));
});

app.listen(3000);
