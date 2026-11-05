const BASE = 'https://api.carrier.example.com/v1';

async function getShipment(ref) {
  const res = await fetch(`${BASE}/shipments/${encodeURIComponent(ref)}`, {
    redirect: 'error',
    signal: AbortSignal.timeout(5000),
    headers: { accept: 'application/json' },
  });
  if (!res.ok) throw new Error(`carrier status ${res.status}`);
  const len = Number(res.headers.get('content-length') || 0);
  if (len > 65536) throw new Error('carrier payload too large');
  const body = await res.json();
  return {
    ref: String(body.ref),
    status: String(body.status),
    labelName: body.label && body.label.filename,
    labelBase64: body.label && body.label.data,
  };
}

module.exports = { getShipment };
