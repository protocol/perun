function setPath(obj, path, value) {
  const keys = path.split(".");
  let cur = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    cur = cur[keys[i]] = cur[keys[i]] || {};
  }
  cur[keys[keys.length - 1]] = value;
  return obj;
}
