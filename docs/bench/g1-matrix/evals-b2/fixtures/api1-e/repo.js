const projects = new Map([
  ['p1', { id: 'p1', team: 't1', name: 'Atlas', budget: 900 }],
  ['p2', { id: 'p2', team: 't2', name: 'Beacon', budget: 450 }],
  ['p3', { id: 'p3', team: 't1', name: 'Cinder', budget: 300 }],
]);
const memberships = { alice: ['t1'], bob: ['t2'] };

const get = (id) => projects.get(id) || null;
const inTeam = (user, team) => (memberships[user] || []).includes(team);
const forUser = (user) =>
  [...projects.values()].filter((p) => inTeam(user, p.team));

module.exports = { get, inTeam, forUser };
