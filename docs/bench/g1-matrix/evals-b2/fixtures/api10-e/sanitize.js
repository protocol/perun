const HANDLE = /^[a-z0-9_]{2,30}$/;
const AVATAR_HOSTS = new Set(['img.directory.example.com', 'cdn.directory.example.com']);

function cleanProfile(raw) {
  const handle = String(raw.handle || '');
  if (!HANDLE.test(handle)) return null;
  let avatar = null;
  try {
    const u = new URL(String(raw.avatar || ''));
    if (u.protocol === 'https:' && AVATAR_HOSTS.has(u.hostname)) avatar = u.href;
  } catch (err) {
    avatar = null;
  }
  return {
    handle,
    displayName: String(raw.displayName || '').replace(/[\u0000-\u001f\u007f<>]/g, '').slice(0, 80),
    avatar,
  };
}

module.exports = { cleanProfile };
