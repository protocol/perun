'use strict';

const express = require('express');
const { requireSession, requireRole } = require('./sessions');
const { halls: hallMap, reservations } = require('./store');

const halls = express.Router();
const legacy = express.Router();


halls.get('/halls/occupancy', (req, res) => { // @@R GET /api/halls/occupancy 0 ; T positive missing_authn route registered above halls.use(requireSession) so the gate never runs and owner ids are returned
  res.json([...reservations.values()].map((r) => ({ hall: r.hallId, owner: r.ownerId, state: r.state })));
});

legacy.get('/guests.json', (req, res) => { // @@R GET /v1/guests.json 0 ; T positive missing_authn legacy v1 router is mounted without any session middleware and lists owner ids and notes
  res.json([...reservations.values()].map((r) => ({ owner: r.ownerId, note: r.note })));
});

halls.use(requireSession);

halls.get('/halls', (req, res) => { // @@R GET /api/halls 1
  res.json([...hallMap.values()].map(({ id, name, open }) => ({ id, name, open })));
});

halls.post('/halls/:id/close', (req, res) => { // @@R POST /api/halls/:id/close 0 ; T positive missing_authz any signed-in guest can close a hall
  const hall = hallMap.get(Number(req.params.id));
  if (!hall) return res.status(404).json({ error: 'not found' });
  hall.open = false;
  return res.json({ id: hall.id, open: hall.open });
});

halls.get('/users/:uid/reservations', (req, res) => { // @@R GET /api/users/:uid/reservations 0 ; T positive missing_object_check path user id used as the filter and never compared with the session user
  const uid = Number(req.params.uid);
  if (!Number.isInteger(uid)) return res.status(400).json({ error: 'bad id' });
  return res.json([...reservations.values()].filter((r) => r.ownerId === uid));
});

halls.patch('/reservations/:id', (req, res) => { // @@R PATCH /api/reservations/:id 0 ; T positive missing_object_check note updated without checking the reservation belongs to the caller
  const found = reservations.get(Number(req.params.id));
  if (!found) return res.status(404).json({ error: 'not found' });
  found.note = String(req.body.note || '').slice(0, 500);
  return res.json(found);
});

halls.get('/me/reservations', (req, res) => { // @@R GET /api/me/reservations 1 ; T decoy missing_authn router gate applies and the list is filtered by the session user id
  res.json([...reservations.values()].filter((r) => r.ownerId === req.session.userId));
});

halls.get('/reservations/:id', (req, res) => { // @@R GET /api/reservations/:id 1 ; T decoy missing_object_check owner compared with the session user and a foreign id answers 404
  const found = reservations.get(Number(req.params.id));
  if (!found || found.ownerId !== req.session.userId) return res.status(404).json({ error: 'not found' });
  return res.json(found);
});

halls.post('/halls/:id/open', requireRole('admin'), (req, res) => { // @@R POST /api/halls/:id/open 1 ; T decoy missing_authz per-route requireRole('admin') middleware array
  const hall = hallMap.get(Number(req.params.id));
  if (!hall) return res.status(404).json({ error: 'not found' });
  hall.open = true;
  return res.json({ id: hall.id, open: hall.open });
});

halls.post('/reservations/:id/cancel', (req, res) => { // @@R POST /api/reservations/:id/cancel 1 ; T decoy missing_object_check cancel allowed only for the owner or an admin and others get 404
  const found = reservations.get(Number(req.params.id));
  const { userId, role } = req.session;
  if (!found || (found.ownerId !== userId && role !== 'admin')) return res.status(404).json({ error: 'not found' });
  found.state = 'cancelled';
  return res.json(found);
});

const admin = express.Router();
admin.use(requireRole('admin'));
halls.use('/admin', admin);

admin.put('/halls/:id/capacity', (req, res) => { // @@R PUT /api/admin/halls/:id/capacity 1 ; T decoy missing_authz admin sub-router guards every route with requireRole('admin')
  const hall = hallMap.get(Number(req.params.id));
  const cap = Number(req.body.capacity);
  if (!hall || !Number.isInteger(cap) || cap < 1 || cap > 500) return res.status(400).json({ error: 'bad request' });
  hall.capacity = cap;
  return res.json(hall);
});

module.exports = { halls, legacy };
