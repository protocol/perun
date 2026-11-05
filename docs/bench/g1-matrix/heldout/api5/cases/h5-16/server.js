const express = require('express');
const mongoose = require('mongoose');
const auth = require('./auth');
const Invoice = require('./models/invoice');

const app = express();
app.use(express.json());

app.get('/invoices', auth, async (req, res) => {
  res.json(await Invoice.find({ owner: req.user.id }));
});

app.patch('/invoices/:id/status', auth, async (req, res) => {
  const doc = await Invoice.findByIdAndUpdate(
    req.params.id,
    { status: req.body.status },
    { new: true }
  );
  res.json(doc);
});

mongoose.connect(process.env.MONGO_URL).then(() => app.listen(8080));
