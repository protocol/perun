module.exports = (req, res, pool) => {
  pool.query(`SELECT * FROM widgets ORDER BY ${req.query.sort}`, (err, rows) => res.json(rows));
};
