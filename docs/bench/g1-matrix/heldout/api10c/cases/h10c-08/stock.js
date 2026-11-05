const axios = require('axios');
const mysql = require('mysql2/promise');

async function refreshStock(sku) {
  const conn = await mysql.createConnection({ host: 'db.example.com', user: 'acme' });
  const res = await axios.get(`https://warehouse.example.com/stock/${encodeURIComponent(sku)}`);
  const qty = Number(res.data.quantity);
  if (!Number.isInteger(qty) || qty < 0) {
    throw new Error('bad quantity');
  }
  await conn.query(`UPDATE stock SET qty = ${qty} WHERE sku = ?`, [sku]);
  await conn.end();
  return qty;
}

module.exports = { refreshStock };
