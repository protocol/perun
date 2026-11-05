const mysql = require("mysql2/promise");
const { asCount } = require("./coerce");

async function getTally(sku) {
  const res = await fetch(`https://stock.example.com/api/tally/${sku}`);
  if (!res.ok) throw new Error(`tally ${res.status}`);
  return res.json();
}

async function record(pool, sku) {
  const t = await getTally(sku);
  const qty = asCount(t.on_hand);
  await pool.query("UPDATE stock SET qty = " + qty + " WHERE sku = " + pool.escape(sku));
  return qty;
}

module.exports = { record };
