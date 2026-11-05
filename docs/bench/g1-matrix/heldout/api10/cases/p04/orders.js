const axios = require("axios");
const mysql = require("mysql2/promise");

async function pullStatus(orderId) {
  const res = await axios.get(`https://shipping.example.com/orders/${orderId}`, {
    timeout: 5000,
  });
  return res.data;
}

async function updateOrder(pool, orderId) {
  const data = await pullStatus(orderId);
  const sql =
    "UPDATE orders SET status = '" + data.status + "' WHERE id = " + Number(orderId);
  await pool.query(sql);
  return data.status;
}

async function main() {
  const pool = mysql.createPool({ host: "db.example.com", user: "acme" });
  console.log(await updateOrder(pool, 12));
  await pool.end();
}

module.exports = { updateOrder };
if (require.main === module) main();
