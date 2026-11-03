const GEO = 'https://geo.vendor.example.com';

type Ctx = { params: Promise<{ code: string }> };

export async function GET(_req: Request, { params }: Ctx) { // @@R GET /api/geo/[code]/history 1
  const { code } = await params;
  if (!/^[a-z]{2}$/.test(code)) {
    return Response.json({ error: 'bad code' }, { status: 400 });
  }
  const res = await fetch(`${GEO}/v1/regions/${code}/history`, { headers: { 'x-api-key': process.env.GEO_KEY ?? '' }, signal: AbortSignal.timeout(5000) }); // @@T decoy secret_in_url key sent in a header, with timeout
  return Response.json(await res.json());
}
