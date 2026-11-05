const knex = require('knex')({ client: 'pg', connection: 'postgres://db.example.com/acme' });

async function fetchCustomer(id) {
  const res = await fetch(`https://crm.example.com/customers/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error('crm lookup failed');
  return res.json();
}

async function tagOrders(customerId) {
  const customer = await fetchCustomer(customerId);
  const rows = await knex.raw(
    'UPDATE orders SET segment = ? WHERE customer_id = ? RETURNING id',
    [customer.segment, customerId]
  );
  return rows.rows.length;
}

async function pending() {
  return knex('orders').where({ status: 'pending' }).count('* as n');
}

module.exports = { tagOrders, pending };
