const ALLOWED_COLS = new Set(['name', 'created_at']);

module.exports = (pool, col, done) => {
  if (!ALLOWED_COLS.has(col)) throw new Error('unsupported sort column');
  pool.query(`SELECT * FROM widgets ORDER BY ${col}`, done);
};
