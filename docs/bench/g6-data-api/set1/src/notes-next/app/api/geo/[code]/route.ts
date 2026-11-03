const GEO = 'https://geo.vendor.example.com';

type Ctx = { params: Promise<{ code: string }> };

export async function GET(_req: Request, { params }: Ctx) { // @@R GET /api/geo/[code] 1
  const { code } = await params;
  if (!/^[a-z]{2}$/.test(code)) {
    return Response.json({ error: 'bad code' }, { status: 400 });
  }
  const res = await fetch(`${GEO}/v1/regions/${code}`, { headers: { 'x-api-key': process.env.GEO_KEY ?? '' } }); // @@T positive no_timeout outbound call without a timeout
  return Response.json(await res.json());
}
