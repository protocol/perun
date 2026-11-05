const MAX_PAGES = 5;

async function getJson(url) {
  const res = await fetch(url, { headers: { accept: 'application/json' } });
  if (!res.ok) throw new Error(`status ${res.status}`);
  return res.json();
}

async function crawlCatalog() {
  const pages = [];
  let page = await getJson('https://catalog.example.com/v2/items');
  pages.push(page.items);
  for (let i = 1; i < MAX_PAGES && page.next_url; i += 1) {
    const follow = await fetch(page.next_url, { method: 'GET' });
    page = await follow.json();
    pages.push(page.items);
  }
  return pages.flat();
}

async function countItems() {
  const items = await crawlCatalog();
  return items.length;
}

module.exports = { crawlCatalog, countItems };
