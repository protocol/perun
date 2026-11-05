const BASE = "https://events.acme-bus.example.com";
const KNOWN = new Set(["hooks.acme-partner.example.com", "relay.acme-bus.example.com"]);

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
  const target = new URL(sub.callback_url);
  if (target.protocol !== "https:" || !KNOWN.has(target.hostname)) {
    return null;
  }
  const out = await fetch(target, {
    method: "POST",
    redirect: "error",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return out.status;
}

module.exports = { relay };
