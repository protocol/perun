const ALLOWED = new Set(['img.example.com', 'static.example.com']);

export async function GET(req: Request) { // @@R GET /api/preview/safe 1
  let target: URL;
  try {
    target = new URL(new URL(req.url).searchParams.get('url') ?? '');
  } catch {
    return Response.json({ error: 'bad url' }, { status: 400 });
  }
  if (target.protocol !== 'https:' || !ALLOWED.has(target.hostname)) {
    return Response.json({ error: 'host not allowed' }, { status: 400 });
  }
  const res = await fetch(target, { redirect: 'error', signal: AbortSignal.timeout(5000) }); // @@T decoy ssrf https plus host allowlist plus no redirects
  return Response.json({ type: res.headers.get('content-type') });
}
