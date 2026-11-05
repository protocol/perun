const { get, inTeam } = require('./repo');

const keys = new Map(Object.entries(JSON.parse(process.env.API_KEYS || '{}')));

function authenticate(req, res, next) {
  const user = keys.get(req.get('x-key'));
  if (!user) return res.status(401).json({ error: 'authentication required' });
  req.user = user;
  next();
}

// Loads the project named in the path and enforces team membership.
function loadProject(req, res, next) {
  const id = String(req.params.id);
  if (!/^p[0-9]{1,6}$/.test(id)) return res.status(400).json({ error: 'bad id' });
  const project = get(id);
  if (!project || !inTeam(req.user, project.team)) {
    return res.status(404).json({ error: 'not found' });
  }
  req.project = project;
  next();
}

module.exports = { authenticate, loadProject };
