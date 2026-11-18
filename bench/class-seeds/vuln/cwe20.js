// Fictional Acme seed: CWE-20 improper input validation (no type or range check on a quantity).
const express = require("express");
const app = express();
app.use(express.json());
const PRICE_CENTS = 250;

app.post("/orders", (req, res) => {
  const qty = req.body.qty;
  const items = new Array(qty).fill("widget");
  res.json({ totalCents: PRICE_CENTS * qty, items });
});
