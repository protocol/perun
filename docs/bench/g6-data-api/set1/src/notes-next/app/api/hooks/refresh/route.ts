import { Agent } from 'undici';

const GEO = 'https://geo.vendor.example.com';
const agent = new Agent({
  connect: { rejectUnauthorized: false }, // @@T positive tls_off certificate verification disabled
});

export async function POST() { // @@R POST /api/hooks/refresh 1
  const res = await fetch(`${GEO}/v1/regions`, {
    headers: { 'x-api-key': process.env.GEO_KEY ?? '' },
    signal: AbortSignal.timeout(5000),
    // @ts-expect-error undici dispatcher option
    dispatcher: agent,
  });
  return Response.json(await res.json());
}
