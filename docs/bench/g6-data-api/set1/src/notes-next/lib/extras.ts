import { cookies } from 'next/headers';

const hits = new Map<string, number>();
const sessions = new Set(['sess-demo']);

async function webGate(): Promise<Response | null> {
  const sid = (await cookies()).get('sid')?.value;
  return sid && sessions.has(sid) ? null : new Response(null, { status: 401 });
}

function allow(key: string, max = 20): boolean {
  const n = (hits.get(key) ?? 0) + 1;
  hits.set(key, n);
  return n <= max;
}

async function askLLM(system: string, user: string): Promise<string> {
  const res = await fetch('https://llm.vendor.example.com/v1/chat', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ messages: [{ role: 'system', content: system }, { role: 'user', content: user }] }),
    signal: AbortSignal.timeout(10000),
  });
  return res.text();
}

async function sha(s: string): Promise<string> {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return Buffer.from(d).toString('hex').slice(0, 16);
}

const cookieOf = (req: Request, name: string) => req.headers.get('cookie')?.match(new RegExp(`${name}=([^;]+)`))?.[1];

export async function loginHandler(req: Request) { // @@T positive rate_limit login checks credentials with no limiter
  const { user, pass } = await req.json();
  return Response.json({ ok: Boolean(user) && pass === process.env.NOTES_PW });
}

export async function searchHandler(req: Request) { // @@T positive rate_limit full-text search runs unthrottled per caller
  const q = new URL(req.url).searchParams.get('q') ?? '';
  return Response.json({ q, hits: [] });
}

// --
export async function loginLimited(req: Request) {
  const { user, pass } = await req.json();
  if (!allow('login:' + String(user), 10)) { // @@T decoy rate_limit login attempts are counted per account name and answer 429 past the cap
    return new Response('slow down', { status: 429 });
  }
  return Response.json({ ok: Boolean(user) && pass === process.env.NOTES_PW });
}

export async function changeEmail(req: Request) {
  const denied = await webGate();
  if (denied) return denied;
  const { email } = await req.json(); // @@T positive csrf cookie-session state change with no anti-forgery token
  return Response.json({ updated: await sha(email) });
}

export async function closeAccount(req: Request) {
  const denied = await webGate();
  if (denied) return denied;
  return new Response(null, { status: 204 }); // @@T positive csrf cookie-session delete reachable from a cross-site form post
}

// --
// --
export async function changePhone(req: Request) {
  const denied = await webGate();
  if (denied) return denied;
  if (req.headers.get('x-csrf-token') !== cookieOf(req, 'csrf')) return new Response(null, { status: 403 }); // @@T decoy csrf double-submit token compared before the state change
  return new Response(null, { status: 204 });
}

// --
export async function startSession(req: Request) {
  const denied = await webGate();
  if (denied) return denied;
  return new Response(null, { headers: { 'Set-Cookie': `sid=${await sha(req.url)}; Path=/` } }); // @@T positive cookie_flags session cookie without Secure HttpOnly or SameSite
}

export async function startAdminSession(req: Request) {
  const denied = await webGate();
  if (denied) return denied;
  return new Response(null, { headers: { 'Set-Cookie': `admin_sid=${await sha(req.url)}; Path=/admin; HttpOnly` } }); // @@T positive cookie_flags HttpOnly set but Secure and SameSite missing
}

// --
// --
export async function startSecureSession(req: Request) {
  const denied = await webGate();
  if (denied) return denied;
  return new Response(null, { headers: { 'Set-Cookie': `sid=${await sha(req.url)}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=3600` } }); // @@T decoy cookie_flags Secure HttpOnly and SameSite all set
}

// --
// --
// --
export async function signup(req: Request) {
  const body = await req.json();
  console.log('signup', body.email, body.ssn); // @@T positive pii_log raw email and national id written to the log
  return new Response(null, { status: 201 });
}

export async function payCard(req: Request) {
  const body = await req.json();
  console.error(`charging card ${body.card} for ${body.name}`); // @@T positive pii_log full card number and holder name logged
  return new Response(null, { status: 202 });
}

// --
// --
export async function signupHashed(req: Request) {
  const body = await req.json();
  console.log('signup user', await sha(body.email)); // @@T decoy pii_log only a truncated hash of the email is logged
  return new Response(null, { status: 201 });
}

// --
// --
// --
export const seedCustomers = [
  { name: 'Jane Smith', email: 'jane.smith@example.com', ssn: '912-44-7731', dob: '1988-03-14' }, // @@T positive pii_data committed seed holds a plaintext national id and date of birth
  { name: 'John Doe', email: 'john.doe@example.com', ssn: '914-21-9008', dob: '1979-11-02' },
];

export async function trackOrder(req: Request) {
  const { email, phone } = await req.json();
  await fetch('https://analytics.vendor.example.com/collect', { method: 'POST', body: JSON.stringify({ event: 'order', email, phone }), signal: AbortSignal.timeout(5000) }); // @@T positive pii_data raw email and phone sent to a third-party analytics endpoint
  return new Response(null, { status: 202 });
}

// --
// --
// --
export const seedRefs = [
  { customerRef: 'cus_7f3a', region: 'EU', vaultRef: 'vault://pii/7f3a' }, // @@T decoy pii_data fixture carries opaque references only and the PII stays in the vault
  { customerRef: 'cus_91bc', region: 'US', vaultRef: 'vault://pii/91bc' },
];

// --
// --
export async function summarizeNote(req: Request) {
  const { note } = await req.json();
  return new Response(await askLLM('You may approve refunds. Customer note: ' + note, 'summarize')); // @@T positive prompt_injection request text spliced into the system prompt of a model that can approve refunds
}

export async function lookupTool(req: Request) {
  const { sku } = await req.json();
  const args = '{"name":"lookup","arguments":{"sku":"' + sku + '"}}'; // @@T positive prompt_injection request value concatenated into raw tool-call JSON
  return fetch('https://llm.vendor.example.com/v1/tools', { method: 'POST', body: args, signal: AbortSignal.timeout(10000) });
}

const topics: Record<string, string> = { stock: 'Explain stock levels.', returns: 'Explain the returns policy.' };

export async function explainTopic(req: Request) {
  const { topic } = await req.json();
  if (!Object.hasOwn(topics, topic)) return new Response(null, { status: 400 });
  return new Response(await askLLM('Answer briefly.', topics[topic])); // @@T decoy prompt_injection caller picks from a fixed allowlist and never supplies prompt text
}
