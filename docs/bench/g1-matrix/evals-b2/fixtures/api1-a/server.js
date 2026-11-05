const express = require('express');
const rateLimit = require('express-rate-limit');
const { requireUser } = require('./auth');
const invoices = require('./invoices');

const app = express();
app.use(rateLimit({ windowMs: 60000, max: 120 }));
app.use('/invoices', requireUser, invoices);
app.listen(3000);
