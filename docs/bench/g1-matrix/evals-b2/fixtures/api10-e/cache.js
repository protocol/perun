const store = new Map();
const MAX_ENTRIES = 1000;

function put(profile) {
  if (store.size >= MAX_ENTRIES) store.delete(store.keys().next().value);
  store.set(profile.handle, { profile, at: Date.now() });
}

function get(handle) {
  const hit = store.get(handle);
  if (!hit || Date.now() - hit.at > 300000) return null;
  return hit.profile;
}

module.exports = { put, get };
