'use strict';

const invoices = new Map([
  [1, { id: 1, ownerId: 10, total: 120, note: 'net30' }],
  [2, { id: 2, ownerId: 11, total: 80, note: 'net15' }],
]);

const clients = new Map([
  [1, { id: 1, ownerId: 10, name: 'Acme Capital' }],
  [2, { id: 2, ownerId: 11, name: 'Globex Partners' }],
]);

const users = new Map([
  [10, { id: 10, role: 'user' }],
  [11, { id: 11, role: 'admin' }],
]);

module.exports = { invoices, clients, users };
