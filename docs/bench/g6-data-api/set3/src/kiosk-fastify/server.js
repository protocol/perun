'use strict';
const Fastify = require('fastify');
const auth = require('./auth');

const app = Fastify({ logger: true });

app.register(require('@fastify/cookie'));
app.register(require('@fastify/formbody'));
app.register(require('@fastify/session'), {
  secret: process.env.KIOSK_SECRET,
  cookie: { secure: true, httpOnly: true, sameSite: 'strict' },
});
app.register(require('@fastify/rate-limit'), { global: false });

app.get('/healthz', async () => ({ ok: true })); // @@R GET /healthz 0 public

app.register(require('./routes/public'));
app.register(require('./routes/gateway'));

app.register(async (scope) => {
  scope.addHook('onRequest', auth.bearerAuth);
  scope.get('/api/me', async (req) => ({ uid: req.user.uid, role: req.user.role })); // @@R GET /api/me 1
  scope.register(require('./routes/records'));
  scope.register(require('./routes/catalog'));
  scope.register(require('./routes/partners'));
  scope.register(require('./routes/integrations'));
});

app.register(async (scope) => {
  scope.addHook('onRequest', auth.cookieAuth);
  scope.register(require('./routes/account'));
});

app.register(async (scope) => {
  scope.addHook('onRequest', auth.memberAuth);
  scope.register(require('./routes/profile'));
});

app.listen({ port: 3000, host: '127.0.0.1' });
