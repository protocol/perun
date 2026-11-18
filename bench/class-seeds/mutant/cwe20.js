// Fictional Acme seed: CWE-20 mutant, renamed, query string parsed with parseInt and never checked.
const express = require("express");
const shop = express();
const UNIT = 250;

shop.get("/cart/price", (request, response) => {
  const count = parseInt(request.query.count);
  const rows = Array.from({ length: count }, () => "gadget");
  response.json({ cents: UNIT * count, rows });
});
