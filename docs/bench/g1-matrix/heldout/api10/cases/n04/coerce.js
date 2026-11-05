function asCount(value) {
  const n = Number(value);
  if (!Number.isInteger(n) || n < 0 || n > 1e9) {
    throw new RangeError("bad count");
  }
  return n;
}

module.exports = { asCount };
