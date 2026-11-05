const BASE = "https://users.acme-identity.example.com/v1";

async function getUser(id) {
  const res = await fetch(`${BASE}/users/${id}`);
  if (!res.ok) throw new Error(`user ${id}: ${res.status}`);
  return res.json();
}

async function getUserRegion(id) {
  const user = await getUser(id);
  return user.region;
}

module.exports = { getUser, getUserRegion };
