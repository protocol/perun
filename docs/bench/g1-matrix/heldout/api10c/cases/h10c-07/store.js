const axios = require('axios');
const mysql = require('mysql2/promise');
const { getVendor } = require('./vendorClient');

async function saveVendor(id) {
  const conn = await mysql.createConnection({ host: 'db.example.com', user: 'acme' });
  const vendor = await getVendor(id);
  await conn.query(`UPDATE vendors SET label = '${vendor.display_name}' WHERE id = ?`, [id]);
  await conn.end();
}

module.exports = { saveVendor };
