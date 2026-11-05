const BASE = "https://users.acme-identity.example.com/v1";
const REGION_COLUMN = { emea: "region_emea", apac: "region_apac", amer: "region_amer" };

async function getUser(id) {
  const res = await fetch(`${BASE}/users/${id}`);
  if (!res.ok) throw new Error(`user ${id}: ${res.status}`);
  return res.json();
}

async function getRegionColumn(id) {
  const user = await getUser(id);
  const col = REGION_COLUMN[user.region];
  if (!col) throw new Error("unmapped region");
  return col;
}

module.exports = { getUser, getRegionColumn };
