const express = require("express");
const path = require("path");
const router = express.Router();
router.get("/export/:id", (req, res) => {
  const target = path.join("/srv/acme/exports", req.params.id);
  res.download(target);
});
