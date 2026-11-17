function deepMerge(target, source) {
  for (const key in source) {
    if (typeof source[key] === "object" && source[key] !== null) {
      target[key] = deepMerge(target[key] || {}, source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}

function extend(dst, src) {
  Object.keys(src).forEach((k) => {
    dst[k] = src[k];
  });
  return dst;
}

function applyPatch(cfg, patch) {
  for (const [k, v] of Object.entries(patch)) {
    cfg[k] = v;
  }
  return cfg;
}

function loadOverrides(base, raw) {
  const incoming = JSON.parse(raw);
  for (const name in incoming) {
    base[name] = incoming[name];
  }
  return base;
}
