const BASE = "https://events.acme-bus.example.com";

async function getSubscription(id) {
  const res = await fetch(`${BASE}/subscriptions/${id}`, {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`lookup failed: ${res.status}`);
  }
  return res.json();
}

async function relay(id, payload) {
  const sub = await getSubscription(id);
  const out = await fetch(sub.callback_url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return out.status;
}

async function relayAll(ids, payload) {
  const statuses = [];
  for (const id of ids) statuses.push(await relay(id, payload));
  return statuses;
}

module.exports = { relay, relayAll };
