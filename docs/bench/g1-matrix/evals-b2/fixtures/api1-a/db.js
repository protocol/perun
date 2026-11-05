const invoices = new Map([
  [1, { id: 1, ownerId: 'u1', total: 120, note: 'Acme retainer', status: 'open' }],
  [2, { id: 2, ownerId: 'u2', total: 80, note: 'Globex support', status: 'paid' }],
  [3, { id: 3, ownerId: 'u1', total: 45, note: 'Acme hosting', status: 'open' }],
]);

function findInvoice(id) {
  return invoices.get(id) || null;
}

function listInvoices(ownerId) {
  return [...invoices.values()].filter((inv) => inv.ownerId === ownerId);
}

function saveInvoice(inv) {
  invoices.set(inv.id, inv);
  return inv;
}

module.exports = { findInvoice, listInvoices, saveInvoice };
