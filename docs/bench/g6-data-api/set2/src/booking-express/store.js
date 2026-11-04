'use strict';

const halls = new Map([
  [1, { id: 1, name: 'North Hall', open: true, capacity: 80 }],
  [2, { id: 2, name: 'Garden Room', open: true, capacity: 30 }],
]);

const reservations = new Map([
  [1, { id: 1, ownerId: 40, hallId: 1, note: 'projector needed', state: 'booked' }],
  [2, { id: 2, ownerId: 41, hallId: 2, note: 'vegan catering', state: 'booked' }],
]);

module.exports = { halls, reservations };
