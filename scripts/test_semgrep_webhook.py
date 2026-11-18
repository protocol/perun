#!/usr/bin/env python3
"""Tests for the perun.*.webhook-* rules in templates/semgrep-taint/webhook.yml (CWE-345/347, coverage-matrix row "Webhook signatures"):
a handler whose route path or name contains "webhook" and that reads the request body but never calls a verifier is a finding; the clean
twin (stripe constructEvent, svix verify, octokit verify, createHmac + timingSafeEqual, hmac.compare_digest, a verify*/signature* helper,
a verif* middleware, a signature guard or dependency) stays clean; mutated variants (other names, syntax forms, verifier spellings) keep
the same verdict. Fixtures use `// ruleid: <id>` / `# ruleid: <id>` (next line must be a finding) and `// ok: <id>` / `# ok: <id>` (next
line must stay clean); a finding is reported on the first line of the handler (decorators included). Live check needs semgrep and prints
SKIP without it. Excluded-path files (tests/, *.test.*, *.spec.*, test_*.py, *_test.go, testdata, vendor) carry no annotation and must yield zero findings; semgrep runs with
--x-ignore-semgrepignore-files so its default ignores cannot hide a missing exclude. Fictional names only. RULES=<dir> checks another copy."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
JS, NEST, NEXT, PY, FAPI, GO = ("perun.js.webhook-no-signature-verify", "perun.js.webhook-nest-no-signature-verify",
                            "perun.js.webhook-next-no-signature-verify", "perun.py.webhook-no-signature-verify",
                            "perun.py.webhook-fastapi-no-signature-verify", "perun.go.webhook-no-signature-verify")

# (rule id, relative path) -> source. Vulnerable case, clean twin and mutated variants share a file per rule.
FILES = {
    (JS, "app.js"): f'''
const express = require("express");
const crypto = require("crypto");
const app = express();
const router = express.Router();

// ruleid: {JS}
app.post("/webhooks/billing", express.json(), (req, res) => {{
  queue.push(req.body);
  res.sendStatus(200);
}});

// ruleid: {JS}
async function handleBillingWebhook(req, res) {{
  const event = JSON.parse(await req.text());
  await ledger.apply(event);
  res.sendStatus(200);
}}

// mutated: arrow, other parameter names, other body accessor
// ruleid: {JS}
const onShipmentWebhook = async (request, reply) => {{
  const raw = await request.arrayBuffer();
  await ledger.apply(raw);
  reply.end();
}};

// mutated: router, PUT, mixed-case path, function expression handler
// ruleid: {JS}
router.put("/api/Shipments-Webhook", function (request, reply) {{
  reply.send(request.body);
}});

class HookReceiver {{
  // mutated: class method
  // ruleid: {JS}
  async receiveWebhook(req) {{
    return ledger.apply(req.body);
  }}
}}

// clean twin: stripe constructEvent
// ok: {JS}
app.post("/webhooks/stripe", express.raw({{ type: "application/json" }}), (req, res) => {{
  const event = stripe.webhooks.constructEvent(req.body, req.headers["stripe-signature"], process.env.SIGNING_SECRET);
  queue.push(event);
  res.sendStatus(200);
}});

// clean twin: svix
// ok: {JS}
async function svixWebhook(req, res) {{
  const payload = await req.text();
  const event = new SvixWebhook(secret).verify(payload, req.headers);
  res.json(event);
}}

// clean twin: octokit
// ok: {JS}
const githubWebhook = async (req, res) => {{
  await webhooks.verify(req.body, req.headers["x-hub-signature-256"]);
  res.sendStatus(202);
}};

// clean twin: createHmac + timingSafeEqual
// ok: {JS}
function handleInvoiceWebhook(req, res) {{
  const expected = crypto.createHmac("sha256", secret).update(req.rawBody).digest();
  if (!crypto.timingSafeEqual(expected, Buffer.from(req.headers["x-signature"], "hex"))) return res.sendStatus(401);
  res.sendStatus(200);
}}

// mutated clean: any function named verify*/signature*
// ok: {JS}
async function acmeWebhook(req, res) {{
  if (!checkSignature(req.rawBody, req.headers["x-acme-signature"])) return res.sendStatus(401);
  res.json(req.body);
}}

// mutated clean: verif* middleware in the route arguments
// ok: {JS}
app.post("/webhooks/acme", verifySignature, (req, res) => {{
  res.json(req.body);
}});

// no body read: a health probe on a webhook-named handler
// ok: {JS}
function webhookHealth(req, res) {{
  res.send("ok");
}}

// not a webhook route
// ok: {JS}
app.post("/orders", (req, res) => {{
  res.json(req.body);
}});

// HMAC computed but compared with !==: not constant-time, still a finding
// ruleid: {JS}
function handleLedgerWebhook(req, res) {{
  const expected = crypto.createHmac("sha256", secret).update(req.rawBody).digest("hex");
  if (expected !== req.headers["x-sender-sig"]) return res.sendStatus(401);
  res.sendStatus(200);
}}

// mutated: === compare on a /hooks route
// ruleid: {JS}
app.post("/hooks/ledger", (req, res) => {{
  const expected = crypto.createHmac("sha256", secret).update(req.body).digest("hex");
  if (expected === req.headers["x-sender-sig"]) return res.sendStatus(200);
  res.sendStatus(401);
}});

// /hooks segment, github-style path
// ruleid: {JS}
app.post("/github/hooks", (req, res) => {{
  queue.push(req.body);
  res.sendStatus(200);
}});

// clean twin of /hooks: verif* middleware
// ok: {JS}
app.post("/hooks/stripe", verifySignature, (req, res) => {{
  queue.push(req.body);
  res.sendStatus(200);
}});

// clean twin of the HMAC case: constant-time compare
// ok: {JS}
function handleLedgerWebhookSafe(req, res) {{
  const expected = crypto.createHmac("sha256", secret).update(req.rawBody).digest();
  if (!crypto.timingSafeEqual(expected, Buffer.from(req.headers["x-sender-sig"], "hex"))) return res.sendStatus(401);
  res.sendStatus(200);
}}

// KNOWN LIMIT (false negative): a comment that looks like a verifier call clears the handler
// ok: {JS}
app.post("/webhooks/commented", (req, res) => {{
  // verifySignature(req) goes here
  ledger.apply(req.body);
  res.sendStatus(200);
}});

// GET is not a delivery method
// ok: {JS}
app.get("/webhooks/config", (req, res) => {{
  res.json(req.body);
}});

// "hookshot" and "hooks-admin" are not hook segments
// ok: {JS}
app.post("/hookshot", (req, res) => {{
  res.json(req.body);
}});
// ok: {JS}
app.post("/hooks-admin", (req, res) => {{
  res.json(req.body);
}});

// Fastify: bare verifier as an options value, then inside an array
// ok: {JS}
fastify.post("/webhooks/fast", {{ preHandler: verifySignature }}, async (req, reply) => {{
  return reply.send(req.body);
}});
// ok: {JS}
fastify.post("/webhooks/fast2", {{ preHandler: [verifySignature] }}, async (req, reply) => {{
  return reply.send(req.body);
}});

// body read through ctx.request / this.request / a destructure
// ruleid: {JS}
router.post("/webhooks/koa", async (ctx) => {{
  await ledger.apply(ctx.request.body);
  ctx.status = 200;
}});
class KoaReceiver {{
  // ruleid: {JS}
  async koaWebhook() {{
    return ledger.apply(this.request.body);
  }}
}}
// ruleid: {JS}
async function destructureWebhook(req, res) {{
  const {{ body }} = req;
  await ledger.apply(body);
  res.sendStatus(200);
}}

// chained app.route(path).post(handler)
// ruleid: {JS}
app.route("/webhooks/chain").post((req, res) => {{
  res.json(req.body);
}});
// ok: {JS}
app.route("/webhooks/chain-ok").post(verifySignature, (req, res) => {{
  res.json(req.body);
}});

// constructEvent-prefixed helper is not Stripe's verifier
// ruleid: {JS}
function rowWebhook(req, res) {{
  constructEventFromRow(req.body);
  res.sendStatus(200);
}}

// a name that merely contains "signature" is not a verifier
// ruleid: {JS}
function computeWebhook(req, res) {{
  const sig = computeSignature(req.body);
  if (sig === req.headers["x-sig"]) return res.sendStatus(200);
  res.sendStatus(401);
}}
// ok: {JS}
function validatedWebhook(req, res) {{
  validateWebhookSignature(req.rawBody, req.headers);
  res.sendStatus(200);
}}

// mutants: formData, blob, use, route verbs
// ruleid: {JS}
async function formWebhook(request) {{
  return ledger.apply(await request.formData());
}}
// ruleid: {JS}
async function blobWebhook(request) {{
  return ledger.apply(await request.blob());
}}
// ruleid: {JS}
app.use("/webhooks/mw", (req, res) => {{
  res.json(req.body);
}});
// ruleid: {JS}
app.route("/webhooks/rt", (req, res) => {{
  res.json(req.body);
}});

// names that merely start with verif/validate/check are not signature verifiers
// ruleid: {JS}
function emailWebhook(req, res) {{
  verifyEmail(req.body.address);
  res.sendStatus(200);
}}
// ruleid: {JS}
function typeWebhook(req, res) {{
  validateEventType(req.body);
  res.sendStatus(200);
}}
// a bare verify shorthand is not a signature check
// ruleid: {JS}
fastify.post("/webhooks/short", {{ preHandler: verify }}, async (req, reply) => {{
  return reply.send(req.body);
}});
// vendor async and options variants, and tsscmp, clear
// ok: {JS}
async function stripeAsyncWebhook(req, res) {{
  const event = await stripe.webhooks.constructEventAsync(req.body, req.headers["stripe-signature"], secret);
  res.json(event);
}}
// ok: {JS}
function tsscmpWebhook(req, res) {{
  if (!tsscmp(sign(req.rawBody), req.headers["x-sig"])) return res.sendStatus(401);
  res.sendStatus(200);
}}
// KNOWN LIMIT (false negative): a verifier-looking string clears the handler
// ok: {JS}
app.post("/webhooks/strlimit", (req, res) => {{
  log("verifySignature(");
  res.json(req.body);
}});

// names without signature or hmac never clear
// ruleid: {JS}
function evWebhook(req, res) {{
  verifyEvent(req.body);
  res.json(req.body);
}}
// ruleid: {JS}
function tkWebhook(req, res) {{
  verifyToken(req.body);
  res.json(req.body);
}}
// ruleid: {JS}
function plWebhook(req, res) {{
  verifyPayload(req.body);
  res.json(req.body);
}}
// ruleid: {JS}
function cfWebhook(req, res) {{
  verifyWebhookConfig(req.body);
  res.json(req.body);
}}
// ruleid: {JS}
function ipWebhook(req, res) {{
  checkSenderIp(req);
  res.json(req.body);
}}
// ruleid: {JS}
function bareWebhook(req, res) {{
  verify(req.body);
  res.json(req.body);
}}
// ruleid: {JS}
function capWebhook(req, res) {{
  captcha.verify(req.body.captcha);
  res.json(req.body);
}}

// crypto evidence and signature-named verifiers clear
// ok: {JS}
function scmWebhook(req, res) {{
  scmp(sign(req.body), req.headers.x);
  res.json(req.body);
}}
// ok: {JS}
function scWebhook(req, res) {{
  safeCompare(sign(req.body), req.headers.x);
  res.json(req.body);
}}
// ok: {JS}
function secWebhook(req, res) {{
  secureCompare(sign(req.body), req.headers.x);
  res.json(req.body);
}}
// ok: {JS}
function seWebhook(req, res) {{
  safeEqual(sign(req.body), req.headers.x);
  res.json(req.body);
}}
// ok: {JS}
function ivrWebhook(req, res) {{
  isValidRequest(req, sig);
  res.json(req.body);
}}
// ok: {JS}
function vsigWebhook(req, res) {{
  verify(req.body, sig);
  res.json(req.body);
}}
// ok: {JS}
function vrawWebhook(req, res) {{
  verify(req.rawBody);
  res.json(req.body);
}}
// a secret or headers argument alone is not signature evidence (jwt.verify)
// ruleid: {JS}
function vsecretWebhook(req, res) {{
  jwt.verify(req.headers.authorization, JWT_SECRET);
  res.json(req.body);
}}
// ok: {JS}
function rqWebhook(req, res) {{
  requireSignature(req.body);
  res.json(req.body);
}}
// ok: {JS}
function vhWebhook(req, res) {{
  verifyHmac(req.body);
  res.json(req.body);
}}
// ok: {JS}
function asWebhook(req, res) {{
  assertSignature(req.body);
  res.json(req.body);
}}
// ok: {JS}
function enWebhook(req, res) {{
  ensureSignature(req.body);
  res.json(req.body);
}}
''',
    (NEST, "billing.controller.ts"): f'''
@Controller("billing")
export class BillingController {{
  // ruleid: {NEST}
  @Post("stripe-webhook")
  async handle(@Body() body: any) {{
    return this.service.apply(body);
  }}

  // mutated: raw-body decorator, other path casing
  // ruleid: {NEST}
  @Post("Acme/Webhook")
  async receive(@RawBody() raw: Buffer) {{
    return this.service.apply(raw);
  }}

  // mutated: body through the request object
  // ruleid: {NEST}
  @Post("hook-webhook")
  async viaRequest(@Req() req: any) {{
    return this.service.apply(req.body);
  }}

  // a guard without signature or hmac in its name does not clear
  // ruleid: {NEST}
  @Post("verified-webhook")
  @UseGuards(VerifiedUserGuard)
  async verifiedUser(@Body() body: any) {{
    return this.service.apply(body);
  }}

  // clean twin: method guard (guard first, guard second)
  // ok: {NEST}
  @Post("guarded-webhook")
  @UseGuards(StripeSignatureGuard)
  async guarded(@Body() body: any) {{
    return this.service.apply(body);
  }}

  // ok: {NEST}
  @UseGuards(HmacGuard)
  @Post("guarded2-webhook")
  async guarded2(@Body() body: any) {{
    return this.service.apply(body);
  }}

  // clean twin: verifier call in the body
  // ok: {NEST}
  @Post("manual-webhook")
  async manual(@Req() req: any) {{
    const event = this.stripe.webhooks.constructEvent(req.rawBody, req.headers["stripe-signature"], this.secret);
    return this.service.apply(event);
  }}

  // not a webhook route
  // ok: {NEST}
  @Post("orders")
  async orders(@Body() body: any) {{
    return this.service.apply(body);
  }}
}}

@Controller("github-webhooks")
export class GithubController {{
  // ruleid: {NEST}
  @Post()
  async handle(@Body() body: any) {{
    return this.service.apply(body);
  }}
}}

// class guard without signature or hmac in its name does not clear
@UseGuards(VerifiedUserGuard)
@Controller("verified-webhooks")
export class VerifiedController {{
  // ruleid: {NEST}
  @Post("ingest-webhook")
  async handle(@Body() body: any) {{
    return this.service.apply(body);
  }}
}}

// clean twin: class guard on a webhook controller
@UseGuards(SvixSignatureGuard)
@Controller("svix-webhooks")
export class SvixController {{
  // ok: {NEST}
  @Post("ingest-webhook")
  async handle(@Body() body: any) {{
    return this.service.apply(body);
  }}
}}

// two routes in one webhook controller: the verified one clears, its unverified sibling is flagged
@Controller("two-webhooks")
export class TwoController {{
  // ok: {NEST}
  @Post("verified")
  async verified(@Body() body: any) {{
    this.verifySignature(body);
    return this.service.apply(body);
  }}

  // ruleid: {NEST}
  @Post("open")
  async open(@Body() body: any) {{
    return this.service.apply(body);
  }}
}}

// a bodyless @Post in a webhook controller does not fire
@Controller("ping-webhooks")
export class PingController {{
  // ok: {NEST}
  @Post("ping")
  async ping() {{
    return "pong";
  }}
}}
''',
    (NEXT, "app/api/webhooks/stripe/route.ts"): f'''
// ruleid: {NEXT}
export async function POST(request: Request) {{
  const event = await request.json();
  await ledger.apply(event);
  return new Response("ok");
}}

// ok: {NEXT}
export async function PUT(request: Request) {{
  const raw = await request.text();
  const event = stripe.webhooks.constructEvent(raw, request.headers.get("stripe-signature")!, secret);
  return Response.json(event);
}}

// mutated: arrow export, other receiver name
// ruleid: {NEXT}
export const PATCH = async (req: Request) => {{
  const raw = await req.arrayBuffer();
  return Response.json({{ n: raw.byteLength }});
}};

// no body read
// ok: {NEXT}
export async function DELETE(request: Request) {{
  return new Response(null, {{ status: 204 }});
}}
''',
    (NEXT, "pages/api/stripe-webhook.ts"): f'''
// mutated: pages router, anonymous default export, file name carries the word
// ruleid: {NEXT}
export default async function (req, res) {{
  await ledger.apply(req.body);
  res.status(200).end();
}}
''',
    (NEXT, "pages/api/webhooks/svix.ts"): f'''
// ok: {NEXT}
export default async function handler(req, res) {{
  const payload = await buffer(req);
  const event = new Webhook(secret).verify(payload.toString(), req.headers);
  res.status(200).json(event);
}}
''',
    (NEXT, "pages/api/webhooks/raw.ts"): f'''
// mutated: raw body helper
// ruleid: {NEXT}
export default function handler(req, res) {{
  const raw = getRawBody(req);
  res.status(200).end();
}}
''',
    (NEXT, "app/api/hooks/stripe/route.ts"): f'''
// /hooks directory
// ruleid: {NEXT}
export async function POST(request: Request) {{
  const event = await request.json();
  return Response.json(event);
}}
''',
    (NEXT, "app/api/hooks/svix/route.ts"): f'''
// clean twin of the /hooks directory
// ok: {NEXT}
export async function POST(request: Request) {{
  const raw = await request.text();
  verifySignature(raw, request.headers);
  return Response.json({{ ok: true }});
}}
''',
    (NEXT, "app/api/orders/route.ts"): f'''
// not a webhook path: same code, same verdict as clean
// ok: {NEXT}
export async function POST(request: Request) {{
  const event = await request.json();
  return Response.json(event);
}}
''',
    (NEXT, "pages/api/webhooks/named.ts"): f'''
// the "handler" export name
// ruleid: {NEXT}
export async function handler(req, res) {{
  res.json(req.body);
}}
''',
    (NEXT, "pages/api/hook/x.ts"): f'''
// a hook/ directory is a webhook path
// ruleid: {NEXT}
export default async function handler(req, res) {{
  res.json(req.body);
}}
''',
    (NEXT, "pages/api/WEBHOOK/in.ts"): f'''
// upper-case WEBHOOK directory is a webhook path
// ruleid: {NEXT}
export default async function handler(req, res) {{
  res.json(req.body);
}}
''',
    (NEXT, "app/api/WebHook/route.ts"): f'''
// mixed-case WebHook directory is a webhook path
// ruleid: {NEXT}
export async function POST(request: Request) {{
  return Response.json(await request.json());
}}
''',
    (NEXT, "pages/api/WebHookIn.ts"): f'''
// upper-case WebHook in a file name is a webhook path
// ruleid: {NEXT}
export default async function handler(req, res) {{
  res.json(req.body);
}}
''',
    (PY, "app.py"): f'''
import hmac
import svix
import stripe
from flask import request, Flask
from fastapi import APIRouter

app = Flask(__name__)
router = APIRouter()

# ruleid: {PY}
@app.route("/webhooks/billing", methods=["POST"])
def billing():
    ledger.apply(request.get_json())
    return "", 204

# mutated: csrf_exempt Django-style function view
# ruleid: {PY}
@csrf_exempt
def handle_shipment_webhook(request):
    ledger.apply(request.body)
    return HttpResponse(status=204)

# a plain function that only mentions webhook, no route decorator: not an entry point
# ok: {PY}
def build_webhook_payload():
    return request.get_json()

# HMAC computed but compared with ==: not constant-time, still a finding
# ruleid: {PY}
@app.route("/webhooks/hmac-only", methods=["POST"])
def hmac_only():
    raw = request.get_data()
    expected = hmac.new(SECRET, raw, "sha256").hexdigest()
    if expected == request.headers.get("X-Sender-Sig"):
        return "", 204
    return "", 401

# /hooks segment routes
# ruleid: {PY}
@app.post("/hooks/x")
def hooks_x():
    ledger.apply(request.get_json())
    return "", 204

# ruleid: {PY}
@app.post("/github/hooks")
def github_hooks():
    ledger.apply(request.get_json())
    return "", 204

# clean twin of /hooks: verif* helper
# ok: {PY}
@app.post("/hooks/safe")
def hooks_safe():
    verify_signature(request)
    ledger.apply(request.get_json())
    return "", 204

# clean twin: bare signature decorator (no parentheses)
# ok: {PY}
@app.post("/hooks/bare")
@require_signature
def hooks_bare():
    ledger.apply(request.get_json())
    return "", 204

# clean twin: bare dotted decorator
# ok: {PY}
@app.post("/hooks/bare2")
@auth.verify_hmac
def hooks_bare2():
    ledger.apply(request.get_json())
    return "", 204

# KNOWN LIMIT (false negative): a comment that looks like a verifier call clears the handler
# ok: {PY}
@app.post("/hooks/commented")
def hooks_commented():
    # TODO verify_signature(request) goes here
    ledger.apply(request.get_json())
    return "", 204

# clean twin of the csrf_exempt view
# ok: {PY}
@csrf_exempt
def safe_shipment_webhook(request):
    verify_signature(request)
    ledger.apply(request.body)
    return HttpResponse(status=204)

# GET-only webhook route
# ok: {PY}
@app.route("/webhooks/config", methods=["GET"])
def webhook_config():
    ledger.apply(request.get_json())
    return "", 200

# mutated: FastAPI decorator, async, other request name, other path casing
# ruleid: {PY}
@router.post("/hooks/Acme-Webhook")
async def receive(req):
    body = await req.json()
    return {{"ok": body}}

# mutated: blueprint verb shortcut and form body
# ruleid: {PY}
@bp.post("/payments/webhook")
def payments():
    ledger.apply(request.form)
    return "", 204

# ruleid: {PY}
class InvoiceWebhookView(View):
    def post(self, request):
        ledger.apply(request.body)
        return HttpResponse(status=204)

# clean twin: hmac.compare_digest
# ok: {PY}
@app.route("/webhooks/acme", methods=["POST"])
def acme():
    raw = request.get_data()
    expected = hmac.new(SECRET, raw, "sha256").hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("X-Acme-Signature", "")):
        return "", 401
    return "", 204

# clean twin: stripe construct_event
# ok: {PY}
@app.route("/webhooks/stripe", methods=["POST"])
def stripe_webhook():
    event = stripe.Webhook.construct_event(request.data, request.headers["Stripe-Signature"], SECRET)
    ledger.apply(event)
    return "", 204

# clean twin: svix
# ok: {PY}
@router.post("/webhooks/svix")
async def svix_hook(req):
    payload = await req.body()
    svix.Webhook(SECRET).verify(payload, dict(req.headers))
    return {{"ok": True}}

# mutated clean: helper named verify*/signature*
# ok: {PY}
class GithubWebhookView(View):
    def post(self, request):
        verify_github_signature(request)
        ledger.apply(request.body)
        return HttpResponse(status=204)

# no body read
# ok: {PY}
@app.route("/webhooks/ping")
def ping():
    return "pong"

# not a webhook route
# ok: {PY}
@app.route("/orders", methods=["POST"])
def orders():
    ledger.apply(request.get_json())
    return "", 204

# constant_time_compare clears
# ok: {PY}
@app.route("/webhooks/dj", methods=["POST"])
def dj_hook():
    raw = request.body
    if not constant_time_compare(sign(raw), request.headers.get("X-Sig", "")):
        return "", 401
    return "", 204

# api_route verb
# ruleid: {PY}
@router.api_route("/webhooks/ar", methods=["POST"])
async def ar_hook(request):
    ledger.apply(await request.json())

# Django-style put and patch methods
# ruleid: {PY}
class PutWebhookView(View):
    def put(self, request):
        ledger.apply(request.body)
# ruleid: {PY}
class PatchWebhookView(View):
    def patch(self, request):
        ledger.apply(request.body)

# flask.request / self.request
# ruleid: {PY}
@app.route("/webhooks/fl", methods=["POST"])
def fl_hook():
    ledger.apply(flask.request.get_json())
# ruleid: {PY}
class SelfWebhookView(View):
    def post(self):
        ledger.apply(self.request.body)

# computing a signature is not verifying it
# ruleid: {PY}
@app.route("/webhooks/cmp", methods=["POST"])
def cmp_hook():
    if compute_signature(request.body) == request.headers.get("X-Sig"):
        return "", 204
    return "", 401

# DRF auth/permission classes naming a signature class clear; others do not
# ok: {PY}
class DrfWebhookView(APIView):
    permission_classes = [HasValidSignature]
    def post(self, request):
        ledger.apply(request.data)
# ok: {PY}
class DrfAuthWebhookView(APIView):
    authentication_classes = (HmacAuthentication,)
    def post(self, request):
        ledger.apply(request.data)
# ruleid: {PY}
class DrfOpenWebhookView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        ledger.apply(request.data)

# names that merely start with verif/check are not signature verifiers
# ruleid: {PY}
@app.route("/webhooks/em", methods=["POST"])
def em_hook():
    verify_email(request.body)
    return "", 204
# ruleid: {PY}
@app.route("/webhooks/ty", methods=["POST"])
def ty_hook():
    check_event_type(request.data)
    return "", 204
# a name that merely starts with construct_event is not Stripe's verifier
# ruleid: {PY}
@app.route("/webhooks/opts", methods=["POST"])
def opts_hook():
    event = construct_event_from_row(request.data)
    return "", 204
# a decorator or jwt-style verify without signature evidence does not clear
# ruleid: {PY}
@app.route("/webhooks/hc", methods=["POST"])
@hmac_cache
def hc_hook():
    ledger.apply(request.get_json())
    return "", 204
# ruleid: {PY}
@app.route("/webhooks/jwt", methods=["POST"])
def jwt_hook():
    jwt.verify(request.headers["Authorization"], JWT_SECRET)
    ledger.apply(request.get_json())
    return "", 204
# a bare verifier inside a list clears
# ok: {PY}
@router.post("/webhooks/lst", dependencies=[verify_signature])
async def lst_hook(request):
    ledger.apply(await request.body())

# ruleid: {PY}
class DrfVerifiedWebhookView(APIView):
    permission_classes = [IsVerifiedUser]
    def post(self, request):
        ledger.apply(request.data)

# names without signature or hmac never clear
# ruleid: {PY}
@app.route("/webhooks/tk", methods=["POST"])
def tk_hook():
    verify_token(request.data)
    return "", 204
# ruleid: {PY}
@app.route("/webhooks/ev", methods=["POST"])
def ev_hook():
    verify_event(request.data)
    return "", 204
# ruleid: {PY}
@app.route("/webhooks/vu", methods=["POST"])
@verify_user
def vu_hook():
    ledger.apply(request.get_json())
    return "", 204
# ok: {PY}
@app.route("/webhooks/scmp", methods=["POST"])
def scmp_hook():
    scmp(sign(request.data), request.headers.get("X-Sig"))
    return "", 204
# ok: {PY}
@app.route("/webhooks/raw", methods=["POST"])
def raw_hook():
    svix.verify(request.data, raw_body)
    return "", 204
# ok: {PY}
@app.route("/webhooks/sig", methods=["POST"])
def sig_hook():
    svix.verify(request.data, sig)
    return "", 204
# ok: {PY}
@app.route("/webhooks/as", methods=["POST"])
def as_hook():
    assert_signature(request.data)
    return "", 204
''',
    (GO, "handler.go"): f'''
package main

import (
	"crypto/hmac"
	"io"
	"net/http"
)

// ruleid: {GO}
func handleBillingWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	ledger.Apply(body)
}}

// mutated: method receiver, other parameter name
// ruleid: {GO}
func (s *Server) shipmentWebhook(w http.ResponseWriter, req *http.Request) {{
	body, _ := io.ReadAll(req.Body)
	s.ledger.Apply(body)
}}

// mutated: /hooks route registered with a function literal
func routes(mux *http.ServeMux) {{
	// ruleid: {GO}
	mux.HandleFunc("/hooks/stripe", func(w http.ResponseWriter, r *http.Request) {{
		body, _ := io.ReadAll(r.Body)
		ledger.Apply(body)
	}})
}}

// HMAC computed but compared with ==: not constant-time, still a finding
// ruleid: {GO}
func handleLedgerWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	mac := hmac.New(sha256.New, secret)
	mac.Write(body)
	if hex.EncodeToString(mac.Sum(nil)) == r.Header.Get("X-Sender-Sig") {{
		ledger.Apply(body)
	}}
}}

// clean twin: hmac.Equal
// ok: {GO}
func handleBillingWebhookSafe(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	mac := hmac.New(sha256.New, secret)
	mac.Write(body)
	if !hmac.Equal(mac.Sum(nil), want) {{
		http.Error(w, "bad signature", 401)
		return
	}}
	ledger.Apply(body)
}}

// clean twin: verif* helper
// ok: {GO}
func (s *Server) verifiedWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	if !verifySignature(body, r.Header) {{
		return
	}}
	s.ledger.Apply(body)
}}

// clean twin of the /hooks route
func routesSafe(mux *http.ServeMux) {{
	// ok: {GO}
	mux.HandleFunc("/hooks/safe", func(w http.ResponseWriter, r *http.Request) {{
		body, _ := io.ReadAll(r.Body)
		if !hmac.Equal(sign(body), want) {{
			return
		}}
		ledger.Apply(body)
	}})
}}

// not a webhook route
// ok: {GO}
func handleOrders(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	ledger.Apply(body)
}}

// subtle.ConstantTimeCompare clears
// ok: {GO}
func handleSubtleWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	if subtle.ConstantTimeCompare(sign(body), want) != 1 {{
		return
	}}
	ledger.Apply(body)
}}

// ValidatePayload clears
// ok: {GO}
func handleGithubWebhook(w http.ResponseWriter, r *http.Request) {{
	defer r.Body.Close()
	payload, err := github.ValidatePayload(r, key)
	if err != nil {{
		return
	}}
	ledger.Apply(payload)
}}

// computing a signature is not verifying it
// ruleid: {GO}
func handleComputeWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	if computeSignature(body) == r.Header.Get("X-Sig") {{
		ledger.Apply(body)
	}}
}}

// names that merely start with verif/check are not signature verifiers
// ruleid: {GO}
func handleUserWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	verifyUser(body)
}}
// ruleid: {GO}
func handleLimitWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	checkEventLimit(body)
}}
// ok: {GO}
func handleOptsWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	event, err := webhook.ConstructEventWithOptions(body, r.Header.Get("Stripe-Signature"), secret, opts)
	_, _ = event, err
}}

// names without signature or hmac never clear
// ruleid: {GO}
func handleEventWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	verifyEvent(body)
}}
// ruleid: {GO}
func handleTokenWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	verifyToken(body)
}}
// ok: {GO}
func handleVerifyWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	err := webhook.Verify(body, r.Header.Get("X-Signature"))
	_ = err
}}
// a secret or headers argument alone is not signature evidence
// a ConstructEvent-prefixed helper is not Stripe's verifier
// ruleid: {GO}
func handleRowWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	webhook.ConstructEventFromRow(body)
}}
// ruleid: {GO}
func handleJwtWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	jwt.Verify(r.Header, secret)
	ledger.Apply(body)
}}
// ok: {GO}
func handleScmpWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	scmp(sign(body), want)
}}
''',
    (FAPI, "api.py"): f'''
from fastapi import APIRouter, Depends, Header, Request
router = APIRouter()

# ruleid: {FAPI}
@router.post("/webhooks/billing")
async def billing(event: BillingEvent):
    ledger.apply(event)

# mutated: bytes parameter, sync def, other decorator object
# ruleid: {FAPI}
@api.post("/hooks/Acme-Webhook")
def acme(payload: bytes, x_trace: str = Header(None)):
    ledger.apply(payload)

# mutated: dict parameter
# ruleid: {FAPI}
@router.put("/shipments/webhook")
async def shipments(data: dict):
    ledger.apply(data)

# clean twin: signature dependency on the route
# ok: {FAPI}
@router.post("/webhooks/safe", dependencies=[Depends(verify_signature)])
async def safe(event: BillingEvent):
    ledger.apply(event)

# clean twin: dependency on a parameter
# ok: {FAPI}
@router.post("/webhooks/safe2")
async def safe2(event: BillingEvent, ok: bool = Depends(check_signature)):
    ledger.apply(event)

# clean twin: takes the Request (the other rule judges the body read)
# ok: {FAPI}
@router.post("/webhooks/raw")
async def raw(request: Request, x_sig: str = Header(None)):
    return {{"n": 1}}

# mutated: /hooks segment
# ruleid: {FAPI}
@router.post("/hooks/x")
async def hooks_x(event: BillingEvent):
    ledger.apply(event)

# clean twin: bare signature decorator
# ok: {FAPI}
@router.post("/hooks/bare")
@require_signature
async def hooks_bare(event: BillingEvent):
    ledger.apply(event)

# "hookshot" is not a hook segment
# ok: {FAPI}
@router.post("/hookshot")
async def hookshot(event: BillingEvent):
    ledger.apply(event)

# not a webhook route
# ok: {FAPI}
@router.post("/orders")
async def orders(event: BillingEvent):
    ledger.apply(event)

# mutated: Any annotation
# ruleid: {FAPI}
@router.post("/webhooks/any")
async def any_hook(data: Any):
    ledger.apply(data)

# mutated: api_route verb
# ruleid: {FAPI}
@router.api_route("/webhooks/ar2", methods=["POST"])
async def ar2_hook(payload: bytes):
    ledger.apply(payload)

# a dependency named signature but not verb-led does not clear
# ruleid: {FAPI}
@router.post("/webhooks/cdep", dependencies=[Depends(compute_signature)])
async def cdep_hook(event: BillingEvent):
    ledger.apply(event)

# a dependency without signature or hmac in its name does not clear
# ruleid: {FAPI}
@router.post("/webhooks/dep", dependencies=[Depends(verify_user)])
async def dep_hook(event: BillingEvent):
    ledger.apply(event)
''',
    (JS, "src/receivers.js"): f'''
// outbound client calls are not routes: posting to an incoming webhook from a non-webhook route
app.post("/signup", async (req, res) => {{
  // ok: {JS}
  await axios.post(process.env.SLACK_WEBHOOK_URL, {{ text: req.body.email }});
  res.sendStatus(201);
}});

app.post("/notes", async (req, res) => {{
  // ok: {JS}
  await got.post("https://hooks.example.com/services/T0/B0/X", {{ json: {{ text: req.body.note }} }});
  res.sendStatus(201);
}});

// known false positive: an outbound sender named like webhook
// ruleid: {JS}
async function notifyWebhook(req) {{
  await fetch(NOTIFY_URL, {{ method: "POST", body: JSON.stringify(req.body) }});
}}

// clean twin: svix two-step, receiver built in the handler then verified
// ok: {JS}
app.post("/webhooks/identity", express.raw({{ type: "application/json" }}), (req, res) => {{
  const wh = new Webhook(process.env.IDENTITY_SECRET);
  const evt = wh.verify(req.body, req.headers);
  queue.push(evt);
  res.sendStatus(200);
}});

// a verify call with no receiver built in the handler still fires
// ruleid: {JS}
app.post("/webhooks/identity-plain", (req, res) => {{
  const evt = wh.verify(req.body, req.headers);
  queue.push(evt);
  res.sendStatus(200);
}});

// the handler's own name is not a svix receiver, and SIGNING_KEY does not name a signature
// ruleid: {JS}
async function auditWebhook(req, res) {{
  const claims = jwt.verify(req.headers.authorization, process.env.SIGNING_KEY);
  await ledger.apply(claims.sub, req.body);
}}

// "sig" inside another word does not name a signature
// ruleid: {JS}
app.post("/webhooks/carrier", (req, res) => {{
  carrier.verify(req.body.consignmentId);
  queue.push(req.body);
}});

// sig as its own word, any case, still clears
// ok: {JS}
app.post("/webhooks/case-sig", (req, res) => {{
  webhooks.verify(req.body, headerSig);
  queue.push(req.body);
}});

// ok: {JS}
app.post("/webhooks/case-sig2", (req, res) => {{
  webhooks.verify(req.body, req.headers[SIG_HEADER]);
  queue.push(req.body);
}});

// a flag that skips verification is not a verifier
// ruleid: {JS}
app.post("/webhooks/billing-flag", (req, res) => {{
  if (!config.verifySignature) {{
    ledger.apply(req.body);
  }}
  res.sendStatus(200);
}});

// ruleid: {JS}
app.post("/webhooks/billing-flag2", (req, res) => {{
  if(config.verifySignature) {{
    log.info("strict mode");
  }}
  ledger.apply(req.body);
}});

// ruleid: {JS}
app.post("/webhooks/billing-flag3", (req, res) => {{
  if (config.verifySignature) {{
    log.info("strict mode");
  }}
  ledger.apply(req.body);
}});

// a module-qualified bare verifier still clears
// ok: {JS}
app.post("/webhooks/mod", security.verifySignature, (req, res) => {{
  ledger.apply(req.body);
}});

// clean twin: @octokit/webhooks verifyAndReceive
// ok: {JS}
app.post("/webhooks/github-sdk", async (req, res) => {{
  await webhooks.verifyAndReceive({{ id: req.headers["x-github-delivery"], name: req.headers["x-github-event"], payload: req.body, signature: req.headers["x-hub-signature-256"] }});
  res.sendStatus(202);
}});

// clean twin: Twilio validateRequest
// ok: {JS}
app.post("/webhooks/sms", (req, res) => {{
  if (!twilio.validateRequest(authToken, req.headers["x-twilio-signature"], url, req.body)) return res.sendStatus(403);
  queue.push(req.body);
}});

// a schema validator is not a signature check
// ruleid: {JS}
app.post("/webhooks/schema", (req, res) => {{
  validateRequest(eventSchema, req.body);
  queue.push(req.body);
}});

// known limit: a request parameter not named req or request is not seen
// ok: {JS}
app.post("/webhooks/short", (r, s) => {{
  queue.push(r.body);
  s.end();
}});
''',
    (JS, "src/guarded.controller.ts"): f'''
// a class-level signature guard clears the JS method form and the Nest controller branch, in any guard position
@Controller("webhooks")
@UseGuards(ThrottlerGuard, StripeSignatureGuard)
export class GuardedWebhooksController {{
  // ok: {JS}
  @Post("stripe")
  handleWebhook(@Req() req: Request) {{
    return this.svc.apply(req.body);
  }}
}}

@Controller("billing")
@UseGuards(ThrottlerGuard)
export class ThrottledBillingController {{
  // ruleid: {JS}
  @Post("refund")
  handleRefundWebhook(@Req() req: Request) {{
    return this.svc.apply(req.body);
  }}
}}

@Controller("billing")
@UseGuards(ThrottlerGuard, HmacGuard)
export class SignedBillingController {{
  // ok: {JS}
  @Post("refund")
  handleRefundWebhook(@Req() req: Request) {{
    return this.svc.apply(req.body);
  }}
}}
''',
    (NEST, "partner.controller.ts"): f'''
@Controller("partners")
export class PartnerController {{
  // mutated: PUT
  // ruleid: {NEST}
  @Put("webhooks/acme")
  acme(@Body() body: any) {{
    return this.service.apply(body);
  }}

  // mutated: @Body with a property key
  // ruleid: {NEST}
  @Post("webhooks/gamma")
  gamma(@Body("data") data: any) {{
    return this.service.apply(data);
  }}

  // mutated: PATCH, @Body with a pipe
  // ruleid: {NEST}
  @Patch("webhooks/delta")
  delta(@Body(new ValidationPipe()) body: any) {{
    return this.service.apply(body);
  }}

  // GET is not a delivery method
  // ok: {NEST}
  @Get("webhooks/status")
  status(@Body() body: any) {{
    return this.service.status(body);
  }}
}}

// class guard anywhere in the guard list clears the method branch
@UseGuards(ThrottlerGuard, HmacGuard)
@Controller("billing")
export class GuardedPartnerController {{
  // ok: {NEST}
  @Post("acme-webhook")
  handle(@Body() body: any) {{
    return this.service.apply(body);
  }}
}}
''',
    (PY, "receivers.py"): f'''
from flask import Flask, request
from svix.webhooks import Webhook

app = Flask(__name__)


# clean twin: svix two-step, receiver built in the handler then verified
# ok: {PY}
@app.post("/webhooks/identity")
def identity_hook():
    payload = request.get_data()
    wh = Webhook(SECRET)
    msg = wh.verify(payload, request.headers)
    queue.put(msg)
    return "", 204


# a verify call with no receiver built in the handler still fires
# ruleid: {PY}
@app.post("/webhooks/identity-plain")
def identity_plain_hook():
    msg = wh.verify(request.get_data(), request.headers)
    queue.put(msg)
    return "", 204


# a webhook-named def or helper call is not a svix receiver
# ruleid: {PY}
@app.post("/webhooks/audit")
def auditWebhook():
    event = parse_webhook(request.get_json())
    token_client.verify(request.headers["Authorization"])
    ledger.apply(event)


# a webhook-named class is not a svix receiver
# ruleid: {PY}
class AuditWebhookView(View):
    def post(self, request):
        token_client.verify(request.headers["Authorization"])
        ledger.apply(request.body)


# a flag read is not a verifier
# ruleid: {PY}
@app.post("/webhooks/flag")
def flag_hook():
    if (config.verify_signature):
        log.info("strict")
    ledger.apply(request.get_json())
    return "", 204


# clean twin: slack_sdk SignatureVerifier
# ok: {PY}
@app.post("/webhooks/chat")
def chat_hook():
    if not verifier.is_valid_request(request.get_data(), request.headers):
        return "", 403
    queue.put(request.get_json())
    return "", 204


# clean twin: Twilio RequestValidator
# ok: {PY}
@app.post("/webhooks/sms")
def sms_hook():
    if not RequestValidator(TOKEN).validate(request.url, request.form, request.headers.get("X-Twilio-Signature", "")):
        return "", 403
    queue.put(request.form)
    return "", 204


# a schema validate call is not a signature check
# ruleid: {PY}
@app.post("/webhooks/schema")
def schema_hook():
    event_schema.validate(request.get_json())
    queue.put(request.get_json())
    return "", 204


# an unused verifier definition is not a call
# ruleid: {PY}
class LedgerWebhookView(View):
    def _verify_signature(self, request):
        return True

    def post(self, request):
        ledger.apply(request.body)
        return HttpResponse(status=204)


# @require_POST alone marks a view
# ruleid: {PY}
@require_POST
def refund_webhook(request):
    ledger.apply(request.body)
    return HttpResponse(status=204)
''',
    (FAPI, "receivers_api.py"): f'''
from typing import Annotated, Optional
from fastapi import APIRouter, Body, Depends

router = APIRouter()


# mutated: Annotated body
# ruleid: {FAPI}
@router.post("/webhooks/billing-annotated")
async def billing_annotated(event: Annotated[BillingEvent, Body()]):
    await ledger.apply(event)


# mutated: Optional body
# ruleid: {FAPI}
@router.post("/webhooks/billing-optional")
async def billing_optional(event: Optional[BillingEvent] = None):
    await ledger.apply(event)


# Annotated or Optional dependencies are not a body
# ok: {FAPI}
@router.post("/webhooks/billing-dep")
async def billing_dep(settings: Annotated[Settings, Depends(get_settings)], user: Optional[User] = Depends(get_user)):
    await ledger.touch(settings.region, user.id)


# GET is not a delivery method
# ok: {FAPI}
@router.api_route("/webhooks/search", methods=["GET"])
async def search_hooks(q: Filters):
    return await store.find(q)
''',
    (GO, "receivers.go"): f'''
package main

import (
	"io"
	"net/http"
)

// mutated: ServeHTTP on a webhook-named type
// ruleid: {GO}
func (h *StripeWebhookHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	h.ledger.Apply(body)
}}

// ServeHTTP on another type is not a webhook entry point
// ok: {GO}
func (h *MetricsHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	h.store.Record(body)
}}

// known limit: a request parameter not named r, req or request is not seen
// ok: {GO}
func refundWebhook(w http.ResponseWriter, httpReq *http.Request) {{
	body, _ := io.ReadAll(httpReq.Body)
	ledger.Apply(body)
}}
''',
    (JS, "tests/hook.js"): f'''
// excluded path: vulnerable-shaped, zero findings expected
function billingWebhook(req, res) {{
  queue.push(req.body);
  res.sendStatus(200);
}}
''',
    (JS, "src/billing.test.js"): f'''
// excluded path: vulnerable-shaped, zero findings expected
function billingWebhook(req, res) {{
  queue.push(req.body);
  res.sendStatus(200);
}}
''',
    (JS, "src/billing.spec.js"): f'''
// excluded path: vulnerable-shaped, zero findings expected
function billingWebhook(req, res) {{
  queue.push(req.body);
  res.sendStatus(200);
}}
''',
    (PY, "tests/hook.py"): f'''
# excluded path: vulnerable-shaped, zero findings expected
@app.route("/webhooks/x", methods=["POST"])
def x_hook():
    ledger.apply(request.get_json())
    return "", 204
''',
    (PY, "test_hook.py"): f'''
# excluded path: vulnerable-shaped, zero findings expected
@app.route("/webhooks/x", methods=["POST"])
def x_hook():
    ledger.apply(request.get_json())
    return "", 204
''',
    (GO, "hook_test.go"): f'''
// excluded path: vulnerable-shaped, zero findings expected
package main

func billingWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	ledger.Apply(body)
}}
''',
    (GO, "testdata/hook.go"): f'''
// excluded path: vulnerable-shaped, zero findings expected
package main

func billingWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	ledger.Apply(body)
}}
''',
    (GO, "vendor/hook.go"): f'''
// excluded path: vulnerable-shaped, zero findings expected
package main

func billingWebhook(w http.ResponseWriter, r *http.Request) {{
	body, _ := io.ReadAll(r.Body)
	ledger.Apply(body)
}}
''',
}


def annotated(body, kind, rid):
    return {i + 2 for i, l in enumerate(body.splitlines()) if re.match(rf"\s*(?://|#) {kind}: {re.escape(rid)}$", l)}


WANT = {k: annotated(v, "ruleid", k[0]) for k, v in FILES.items()}
OK = {k: annotated(v, "ok", k[0]) for k, v in FILES.items()}
for rid in (JS, NEST, NEXT, PY, FAPI, GO):
    n_bad = sum(len(w) for k, w in WANT.items() if k[0] == rid)
    n_ok = sum(len(o) for k, o in OK.items() if k[0] == rid)
    assert n_bad >= 3 and n_ok >= 3, (rid, n_bad, n_ok)

rules = open(os.path.join(RULES, "webhook.yml")).read()
for rid in (JS, NEST, NEXT, PY, FAPI, GO):
    assert f"- id: {rid}\n" in rules, rid

if os.environ.get("REQUIRE_SEMGREP") and not shutil.which("semgrep"):
    raise SystemExit("FAIL: REQUIRE_SEMGREP=1 but semgrep is not installed")
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for (rid, rel), src in FILES.items():
            p = os.path.join(d, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").write(src)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        # the whole rules dir must load together, as the review pipeline loads it
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--x-ignore-semgrepignore-files", "--json", "--quiet", "--", "."],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    for rid in (JS, NEST, NEXT, PY, FAPI, GO):
        got = {(os.path.normpath(x["path"]), x["start"]["line"]) for x in r["results"] if x["check_id"].endswith(rid)}
        want = {(os.path.normpath(rel), n) for (i, rel), w in WANT.items() if i == rid for n in w}
        assert got == want, (rid, "unexpected", sorted(got - want), "missed", sorted(want - got))
    print("semgrep-webhook: live ok")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-webhook: ok")
