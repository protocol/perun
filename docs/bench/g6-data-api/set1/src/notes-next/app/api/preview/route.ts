export async function GET(req: Request) { // @@R GET /api/preview 1
  const target = new URL(req.url).searchParams.get('url') ?? '';
  const res = await fetch(target, { signal: AbortSignal.timeout(5000) }); // @@T positive ssrf caller-controlled URL fetched server side
  const text = await res.text();
  return Response.json({ type: res.headers.get('content-type'), bytes: text.length });
}
