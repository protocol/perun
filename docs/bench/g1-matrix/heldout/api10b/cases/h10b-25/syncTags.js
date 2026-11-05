const { Pool } = require("pg");

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const TAG_API = "https://tags.acme-content.example.com/v1";

async function fetchTag(id) {
  const res = await fetch(`${TAG_API}/tags/${id}`);
  if (!res.ok) throw new Error(`tag service ${res.status}`);
  return res.json();
}

async function findArticles(tagId) {
  const tag = await fetchTag(tagId);
  const result = await pool.query(
    "SELECT id, title FROM articles WHERE category = $1",
    [tag.category]
  );
  return result.rows;
}

async function main() {
  const rows = await findArticles(process.argv[2]);
  for (const row of rows) console.log(row.id, row.title);
  await pool.end();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
