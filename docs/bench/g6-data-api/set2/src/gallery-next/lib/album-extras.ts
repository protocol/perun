import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { albums } from '@/lib/db';
import { closeSession, openSession, withSession, withWeb } from '@/lib/session';
import { SITE, chat, fixedWindow, readCapped, same } from '@/lib/util';

const emailWindow = fixedWindow(5, 60 * 60 * 1000);
const bad = (error: string) => Response.json({ error }, { status: 400 });

export const emailAlbum = withSession(async (_req, _ctx, s) => {
  if (!emailWindow(`user:${s.userId}`)) { // @@T decoy rate_limit sends counted per signed-in user in an hourly window that expires and answered 429 past the cap
    return Response.json({ error: 'too many requests' }, { status: 429, headers: { 'retry-after': '3600' } });
  }
  return new Response(null, { status: 202 });
});

export const printPreview = withSession(async (_req, ctx) => {
  const { id } = await ctx.params;
  if (!/^[0-9]{1,9}$/.test(id)) return bad('bad id');
  const up = await fetch(`https://print.vendor.example.com/preview/${id}.png`, { redirect: 'error', signal: AbortSignal.timeout(5000) }); // @@T decoy ssrf host fixed in code and the caller supplies only a validated numeric id with redirects refused
  const bytes = await readCapped(up, 4 << 20);
  if (!bytes) return Response.json({ error: 'too large' }, { status: 502 });
  return new Response(bytes, { headers: { 'content-type': 'image/png' } });
});

export const geoLookup = withSession(async (_req, ctx) => {
  const { place } = await ctx.params;
  if (!/^[a-z-]{2,40}$/.test(place)) return bad('bad place');
  const up = await fetch(`https://geo.vendor.example.com/v2/places/${place}`, { headers: { 'x-api-key': process.env.GEO_KEY ?? '' }, signal: AbortSignal.timeout(5000) }); // @@T decoy secret_in_url vendor key carried in a request header and the URL holds only the validated place slug
  return new Response(await up.text(), { headers: { 'content-type': 'application/json' } });
});

export const changePhone = withWeb(async (req) => {
  if (req.headers.get('origin') !== SITE) return Response.json({ error: 'bad origin' }, { status: 403 }); // @@T decoy csrf Origin header must equal the site origin and a missing header is rejected
  const body = (await req.json().catch(() => ({}))) as { phone?: unknown };
  if (!/^\+[0-9]{8,15}$/.test(String(body.phone ?? ''))) return bad('bad phone');
  return new Response(null, { status: 204 });
});

export const changeName = withWeb(async (req, _ctx, s) => {
  if (!same(req.headers.get('x-csrf-token') ?? '', s.csrf)) return Response.json({ error: 'bad token' }, { status: 403 }); // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
  const body = (await req.json().catch(() => ({}))) as { name?: unknown };
  if (String(body.name ?? '').length > 60) return bad('bad name');
  return new Response(null, { status: 204 });
});

export const rotateSession = withWeb(async (req, _ctx, s) => {
  if (!same(req.headers.get('x-csrf-token') ?? '', s.csrf)) return Response.json({ error: 'bad token' }, { status: 403 });
  closeSession((await cookies()).get('sid')?.value);
  const res = new NextResponse(null, { status: 204 });
  res.cookies.set('sid', openSession(s.userId, s.role), { path: '/', maxAge: 3600, secure: true, httpOnly: true, sameSite: 'lax' }); // @@T decoy cookie_flags Secure HttpOnly and SameSite all set with a one hour lifetime
  return res;
});

export const redeem = withSession(async (req, _ctx, s) => {
  const body = (await req.json().catch(() => ({}))) as { card?: unknown };
  const card = String(body.card ?? '');
  if (!/^[0-9]{12,19}$/.test(card)) return bad('bad card');
  console.log('redeem accepted', s.userId, card.slice(-4)); // @@T decoy pii_log only the numeric user id and the last four digits are logged
  return new Response(null, { status: 202 });
});

export const notify = withSession(async (req, _ctx, s) => {
  const body = (await req.json().catch(() => ({}))) as { album?: unknown };
  const album = Number(body.album);
  if (albums.get(album)?.ownerId !== s.userId) return Response.json({ error: 'not found' }, { status: 404 });
  await fetch('https://hooks.vendor.example.com/albums', { method: 'POST', body: JSON.stringify({ album }), signal: AbortSignal.timeout(5000) }); // @@T decoy pii_data webhook payload carries only the numeric album id
  return new Response(null, { status: 202 });
});

export const visit = withSession(async (_req, _ctx, s) => {
  await fetch('https://analytics.vendor.example.com/collect', { method: 'POST', body: JSON.stringify({ event: 'visit', user: s.userId }), signal: AbortSignal.timeout(5000) }); // @@T decoy pii_data analytics payload carries the internal numeric id and no direct identifier
  return new Response(null, { status: 202 });
});

export const ask = withSession(async (req) => {
  const body = (await req.json().catch(() => ({}))) as { question?: unknown };
  const q = String(body.question ?? '');
  if (!q || q.length > 500) return bad('bad question');
  const text = await chat([{ role: 'system', content: 'Answer questions about gallery opening hours and print sizes only.' }, { role: 'user', content: q }]); // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
  return new Response(text);
});
