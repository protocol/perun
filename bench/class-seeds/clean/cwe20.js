// Fictional Acme seed: CWE-20 fixed twin (integer and range check before use).
const express = require("express");
const app = express();
app.use(express.json());
const PRICE_CENTS = 250;

app.post("/orders", (req, res) => {
  const qty = req.body.qty;
  if (!Number.isInteger(qty) || qty < 1 || qty > 100) {
    return res.status(400).json({ error: "qty must be an integer from 1 to 100" });
  }
  const items = new Array(qty).fill("widget");
  res.json({ totalCents: PRICE_CENTS * qty, items });
});
