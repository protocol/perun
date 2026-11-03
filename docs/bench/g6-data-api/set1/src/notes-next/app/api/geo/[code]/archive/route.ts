const GEO = 'https://geo.vendor.example.com';

type Ctx = { params: Promise<{ code: string }> };

export async function GET(_req: Request, { params }: Ctx) { // @@R GET /api/geo/[code]/archive 1
  const { code } = await params;
  if (!/^[a-z]{2}$/.test(code)) {
    return Response.json({ error: 'bad code' }, { status: 400 });
  }
  const url = `${GEO}/v1/regions/${code}/archive?key=${process.env.GEO_KEY}`; // @@T positive secret_in_url API key in the query string
  const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
  return Response.json(await res.json());
}
