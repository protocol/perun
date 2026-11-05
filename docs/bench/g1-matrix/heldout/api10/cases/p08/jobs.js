async function getJob(id) {
  const res = await fetch(`https://jobs.example.com/v2/jobs/${id}`, {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`jobs api ${res.status}`);
  }
  return res.json();
}

async function notifyCallback(id, result) {
  const job = await getJob(id);
  const out = await fetch(job.callback_url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, result }),
  });
  return out.status;
}

module.exports = { getJob, notifyCallback };
