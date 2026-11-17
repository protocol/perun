function mergeSkipProto(target, source) {
  for (const key in source) {
    if (key === "__proto__" || key === "constructor" || key === "prototype") continue;
    target[key] = source[key];
  }
  return target;
}

function copyIntoFresh(source) {
  const out = {};
  for (const key of Object.keys(source)) {
    out[key] = source[key];
  }
  return out;
}

function copyIntoNullProto(source) {
  const out = Object.create(null);
  for (const key in source) {
    out[key] = source[key];
  }
  return out;
}

function pickFixed(source) {
  const picked = {};
  for (const field of ["name", "email", "role"]) {
    picked[field] = source[field];
  }
  return picked;
}

function mapMerge(source) {
  const m = new Map();
  for (const key in source) {
    m.set(key, source[key]);
  }
  return m;
}

function fillGrid(grid, n) {
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      grid[i][j] = 0;
    }
  }
  return grid;
}

function setSegmentSafe(obj, path, value) {
  const seg = path.split(".")[0];
  if (seg === "__proto__" || seg === "constructor" || seg === "prototype") throw new Error("bad key");
  obj[seg] = value;
}

function mergeBraceReturn(target, source) {
  for (const key in source) {
    if (key === "__proto__") {
      return target;
    }
    target[key] = source[key];
  }
  return target;
}

function mergeBraceThrow(target, source) {
  for (const key in source) {
    if (!Object.hasOwn(target, key)) {
      throw new Error("unknown key");
    }
    target[key] = source[key];
  }
  return target;
}
