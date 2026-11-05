async function fetchConfig(tenant) {
  const res = await fetch(`https://config.example.com/tenants/${encodeURIComponent(tenant)}`);
  if (!res.ok) throw new Error('config unavailable');
  return res.json();
}

module.exports = { fetchConfig };
