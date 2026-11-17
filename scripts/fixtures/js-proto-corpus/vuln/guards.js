function wrongVariable(t, s, x) {
  for (const k in s) {
    if (x === "__proto__") continue;
    t[k] = s[k];
  }
  return t;
}

function siblingBranch(t, s, flag) {
  for (const k in s) {
    if (flag) {
      if (k === "__proto__") continue;
    }
    t[k] = s[k];
  }
  return t;
}

function unrelated(v) {
  if (v === "__proto__") return null;
  return v;
}

function crossFunction(t, s) {
  for (const k in s) {
    t[k] = s[k];
  }
  return t;
}

function orWrapper(t, s, extra) {
  for (const k in s) {
    if (k !== "__proto__" || extra) {
      t[k] = s[k];
    }
  }
  return t;
}

function positiveHasWrapper(t, s, cache) {
  for (const k in s) {
    if (cache.has(k)) {
      t[k] = s[k];
    }
  }
  return t;
}
