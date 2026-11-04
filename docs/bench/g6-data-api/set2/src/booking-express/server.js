'use strict';

const express = require('express');
const cookieParser = require('cookie-parser');
const { halls, legacy } = require('./halls');

const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '100kb' }));
app.use(express.urlencoded({ extended: false, limit: '100kb' }));
app.use(cookieParser());

app.use('/api', halls);
app.use('/v1', legacy);
app.use(require('./catering-extras'));
app.use(require('./venue-extras'));

app.listen(3000, '127.0.0.1');
