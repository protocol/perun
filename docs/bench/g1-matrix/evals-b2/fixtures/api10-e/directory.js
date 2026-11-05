const BASE = 'https://people.directory.example.com/api';

async function fetchProfile(handle) {
  const res = await fetch(`${BASE}/profiles/${encodeURIComponent(handle)}`, {
    redirect: 'error',
    signal: AbortSignal.timeout(4000),
    headers: { accept: 'application/json' },
  });
  if (!res.ok) throw new Error(`directory status ${res.status}`);
  if (!(res.headers.get('content-type') || '').startsWith('application/json')) {
    throw new Error('directory content type');
  }
  const chunks = [];
  let size = 0;
  for await (const chunk of res.body) {
    size += chunk.length;
    if (size > 32768) throw new Error('directory payload too large');
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString());
}

module.exports = { fetchProfile };
