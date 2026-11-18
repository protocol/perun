const SORT_COLUMNS = { name: 'name', date: 'created_at' };

function pickSortColumn(input) {
  return SORT_COLUMNS[input] ?? 'created_at';
}

module.exports = (pool, sort, done) => {
  const col = pickSortColumn(sort);
  pool.query(`SELECT * FROM widgets ORDER BY ${col}`, done);
};
