async function getProfile(id) {
  const res = await fetch(`https://crm.example.com/api/contacts/${id}`);
  if (!res.ok) throw new Error(`crm ${res.status}`);
  return res.json();
}

async function subscribe(id) {
  const contact = await getProfile(id);
  console.log("subscribing", contact.email.length, "chars");
  const out = await fetch("https://mailer.example.com/api/subscribers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: contact.email, name: contact.display_name }),
  });
  if (!out.ok) throw new Error(`mailer ${out.status}`);
  return out.json();
}

module.exports = { subscribe };
