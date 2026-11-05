const express = require('express');
const rateLimit = require('express-rate-limit');
const { authenticate } = require('./policy');
const projects = require('./projects');

const app = express();
app.disable('x-powered-by');
app.use(rateLimit({ windowMs: 60000, max: 100 }));
app.use('/projects', authenticate, projects);
app.listen(4000);
