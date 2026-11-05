const mysql = require("mysql2/promise");
const { getRegionColumn } = require("./userApi");

async function ordersForUser(userId) {
  const column = await getRegionColumn(userId);
  const conn = await mysql.createConnection(process.env.DB_URL);
  const [rows] = await conn.query(
    "SELECT * FROM orders WHERE " + column + " = 1 ORDER BY created DESC"
  );
  await conn.end();
  return rows;
}

async function latestOrder(userId) {
  const rows = await ordersForUser(userId);
  return rows[0] || null;
}

module.exports = { ordersForUser, latestOrder };
