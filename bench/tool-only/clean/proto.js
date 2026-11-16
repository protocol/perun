function merge(target, source) {
  for (const key in source) {
    if (!Object.hasOwn(source, key)) continue;
    if (key === '__proto__' || key === 'constructor' || key === 'prototype') continue;
    if (typeof source[key] === 'object' && source[key] !== null) {
      target[key] = merge(target[key] || {}, source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}

module.exports = (req, res) => res.json(merge({}, JSON.parse(req.body)));
