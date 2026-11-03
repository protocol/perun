const GEO = 'https://geo.vendor.example.com';

type Ctx = { params: Promise<{ code: string }> };

export async function GET(_req: Request, { params }: Ctx) { // @@R GET /api/geo/[code]/digest 1
  const { code } = await params;
  if (!/^[a-z]{2}$/.test(code)) {
    return Response.json({ error: 'bad code' }, { status: 400 });
  }
  console.log('digest call using key', process.env.GEO_KEY); // @@T positive secret_in_log key written to the log
  const res = await fetch(`${GEO}/v1/regions/${code}/digest`, { headers: { 'x-api-key': process.env.GEO_KEY ?? '' }, signal: AbortSignal.timeout(5000) });
  return Response.json(await res.json());
}
