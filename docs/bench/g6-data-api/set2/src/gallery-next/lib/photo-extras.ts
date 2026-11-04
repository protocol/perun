import https from 'node:https';
import { NextResponse } from 'next/server';
import { randomBytes } from 'node:crypto';
import { openSession, withRole, withSession, withWeb } from '@/lib/session';
import { chat, same } from '@/lib/util';

const CATALOG = 'https://catalog.vendor.example.com';
const FORECAST = 'https://forecast.vendor.example.com';
const RADAR = 'https://radar.vendor.example.com';
const sms = 'https://sms.vendor.example.com/v1/send';
const key = (name: string) => process.env[name] ?? '';
const bad = (error: string) => Response.json({ error }, { status: 400 });

export const embed = withSession(async (req) => {
  const target = new URL(req.url).searchParams.get('target') ?? '';
  const up = await fetch(target, { signal: AbortSignal.timeout(5000) }); // @@T positive ssrf caller-supplied URL fetched from the server
  return new Response(await up.text(), { headers: { 'content-type': 'text/html' } });
});

export const refreshCatalog = withRole('admin', () =>
  new Promise<Response>((resolve) => {
    const agent = new https.Agent({ rejectUnauthorized: false }); // @@T positive tls_off certificate verification disabled for the vendor request
    https.get(`${CATALOG}/v1/items`, { agent, timeout: 5000, headers: { 'x-api-key': key('CATALOG_KEY') } }, (up) => {
      up.resume();
      resolve(Response.json({ status: up.statusCode }));
    }).on('error', () => resolve(Response.json({ error: 'upstream unavailable' }, { status: 502 })));
  }));

export const forecast = withSession(async (_req, ctx) => {
  const { city } = await ctx.params;
  if (!/^[a-z]{2,30}$/.test(city)) return bad('bad city');
  const up = await fetch(`${FORECAST}/v3/forecast/${city}`, { headers: { 'x-api-key': key('FORECAST_KEY') } }); // @@T positive no_timeout fetch has no abort signal so a slow vendor holds the request open
  return new Response(await up.text(), { headers: { 'content-type': 'application/json' } });
});

export const alerts = withSession(async (_req, ctx) => {
  const { city } = await ctx.params;
  if (!/^[a-z]{2,30}$/.test(city)) return bad('bad city');
  const up = await fetch(`${FORECAST}/v3/alerts/${city}?key=${key('FORECAST_KEY')}`, { signal: AbortSignal.timeout(5000) }); // @@T positive secret_in_url vendor key appended to the query string
  return new Response(await up.text(), { headers: { 'content-type': 'application/json' } });
});

export const radar = withSession(async () => {
  const token = key('RADAR_KEY');
  const up = await fetch(`${RADAR}/v1/tiles`, { headers: { authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(5000) });
  if (!up.ok) console.error('radar request failed', up.status, token); // @@T positive secret_in_log vendor bearer token written to the error log
  return Response.json({ status: up.status });
});

export async function pinLogin(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { pin?: unknown };
  const want = key('GALLERY_PIN');
  if (!want || !same(String(body.pin ?? ''), want)) return Response.json({ error: 'wrong pin' }, { status: 401 }); // @@T positive rate_limit pin attempts are unlimited so the code can be brute forced
  return Response.json({ token: openSession(40, 'member') });
}

export async function sendCode(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { phone?: unknown };
  const phone = String(body.phone ?? '');
  if (!/^\+[0-9]{8,15}$/.test(phone)) return bad('bad phone');
  await fetch(sms, { method: 'POST', body: JSON.stringify({ to: phone }), signal: AbortSignal.timeout(5000) }); // @@T positive rate_limit text messages can be requested without any cap per number or caller
  return new Response(null, { status: 202 });
}

export const changeEmail = withWeb(async (req) => {
  const body = (await req.json().catch(() => ({}))) as { email?: unknown };
  if (!/^[^@\s]+@[^@\s]+$/.test(String(body.email ?? ''))) return bad('bad email');
  return new Response(null, { status: 204 }); // @@T positive csrf cookie-authenticated email change with no token or origin check
});

export const closeAccount = withWeb(async () => {
  return new Response(null, { status: 204 }); // @@T positive csrf cookie-authenticated account closure with no token or origin check
});

export const rememberDevice = withWeb(async () => {
  const res = new NextResponse(null, { status: 204 });
  res.cookies.set('device', randomBytes(16).toString('hex'), { path: '/' }); // @@T positive cookie_flags device cookie set with no Secure HttpOnly or SameSite attributes
  return res;
});

export const trustDevice = withWeb(async () => {
  const res = new NextResponse(null, { status: 204 });
  res.cookies.set('trusted', randomBytes(16).toString('hex'), { path: '/', maxAge: 31536000 }); // @@T positive cookie_flags year-long cookie with only a lifetime and no Secure HttpOnly or SameSite
  return res;
});

export async function signup(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { email?: string; name?: string };
  console.log('signup received', body.name, body.email); // @@T positive pii_log full name and email address written to the application log
  return new Response(null, { status: 202 });
}

export const charge = withSession(async (req) => {
  const body = (await req.json().catch(() => ({}))) as { card?: string };
  console.log('charge request', body.card); // @@T positive pii_log full card number written to the application log
  return new Response(null, { status: 202 });
});

export const invite = withSession(async (req) => {
  const body = (await req.json().catch(() => ({}))) as { name?: string; email?: string; phone?: string };
  await fetch('https://llm.vendor.example.com/v1/compose', { method: 'POST', body: JSON.stringify({ guest: body }), signal: AbortSignal.timeout(5000) }); // @@T positive pii_data guest name email and phone sent whole to the model vendor
  return new Response(null, { status: 202 });
});

export const track = withSession(async (req, _ctx, s) => {
  const body = (await req.json().catch(() => ({}))) as { email?: string };
  await fetch('https://analytics.vendor.example.com/collect', { method: 'POST', body: JSON.stringify({ event: 'visit', user: s.userId, email: body.email }), signal: AbortSignal.timeout(5000) }); // @@T positive pii_data member email address included in the analytics payload
  return new Response(null, { status: 202 });
});

export const assistNote = withSession(async (req) => {
  const body = (await req.json().catch(() => ({}))) as { note?: string };
  const text = await chat([{ role: 'system', content: `You caption photos for the gallery. Follow the note exactly: ${body.note}` }]); // @@T positive prompt_injection request text interpolated into the system prompt
  return new Response(text);
});

export const assistLookup = withSession(async (req) => {
  const body = (await req.json().catch(() => ({}))) as { place?: string };
  const call = '{"name":"place_lookup","arguments":{"place":"' + body.place + '"}}'; // @@T positive prompt_injection request text concatenated into the tool-call JSON string
  const up = await fetch('https://llm.vendor.example.com/v1/tools', { method: 'POST', body: call, signal: AbortSignal.timeout(5000) });
  return new Response(await up.text());
});
