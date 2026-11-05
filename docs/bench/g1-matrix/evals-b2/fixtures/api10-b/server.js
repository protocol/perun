const express = require('express');
const routes = require('./routes');

const app = express();
app.use(express.json({ limit: '8kb' }));
app.use(routes);
app.listen(3100);
