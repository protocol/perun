<?php

use App\Support\Store;
use App\Support\Vendor;
use GuzzleHttp\Client;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Route;
use Symfony\Component\HttpFoundation\Cookie;

Route::get('/api/ext/reef/{id}/image', function (string $id) { // @@R GET /api/ext/reef/{id}/image 1
    abort_unless(ctype_digit($id), 400);
    $upstream = (new Client(['timeout' => 5, 'allow_redirects' => false]))->get("https://img.vendor.example.com/p/{$id}.jpg"); // @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id with redirects off
    return response((string) $upstream->getBody(), 200, ['Content-Type' => 'image/jpeg']);
});

Route::get('/api/ext/shoal/{code}/rates', function (string $code) { // @@R GET /api/ext/shoal/{code}/rates 1
    abort_unless(preg_match('/^[A-Z]{2}$/', $code) === 1, 400);
    $upstream = (new Client(['timeout' => 5]))->get(Vendor::BASE . "/v1/rates/{$code}", ['headers' => ['X-Api-Key' => Vendor::key()]]); // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
    return response()->json(json_decode((string) $upstream->getBody(), true));
});

Route::get('/api/ext/spire/{code}/stock', function (string $code) { // @@R GET /api/ext/spire/{code}/stock 1
    abort_unless(preg_match('/^[A-Z]{2}$/', $code) === 1, 400);
    $upstream = (new Client(['timeout' => 5]))->get(Vendor::BASE . "/v1/stock/{$code}", ['headers' => ['X-Api-Key' => Vendor::key()]]);
    Log::info("stock lookup code={$code} status={$upstream->getStatusCode()}"); // @@T decoy secret_in_log only the status and the validated code are logged
    return response()->json(json_decode((string) $upstream->getBody(), true));
});

Route::middleware('throttle:5,1')->get('/api/ext/fennel/export', function () { // @@R GET /api/ext/fennel/export 1 ; T decoy rate_limit throttle middleware caps the export at five calls a minute per client
    return response()->json(array_map(fn ($i) => ['i' => $i, 'label' => "fennel-{$i}"], range(0, 99999)));
});

Route::post('/api/ext/ledger/rotate-key', function (Request $request) { // @@R POST /api/ext/ledger/rotate-key 1
    $keyId = bin2hex(random_bytes(8));
    Log::info('rotate user=' . Store::user($request)['uid'] . ' domain=' . explode('@', Store::user($request)['email'])[1] . ' key_id=' . substr($keyId, 0, 6)); // @@T decoy pii_log the log line carries the numeric user id the email domain and a six character key id and no address or key
    return response()->json(['key_id' => $keyId]);
});

Route::post('/api/ext/depot/track', function (Request $request) { // @@R POST /api/ext/depot/track 1
    (new Client(['timeout' => 5]))->post('https://stats.vendor.example.com/v1/event', ['json' => ['event' => 'view', 'uid' => Store::user($request)['uid']]]); // @@T decoy pii_data analytics payload carries the internal numeric id and no direct identifier
    return response()->noContent();
});

$seedharbor = [['label' => 'Sample thread', 'region' => 'north', 'count' => 3]]; // @@T decoy pii_data seed rows hold labels and counts and no person

Route::get('/api/ext/harbor/sample', function () use ($seedharbor) { // @@R GET /api/ext/harbor/sample 1
    return response()->json(['count' => count($seedharbor)]);
});

Route::post('/api/ext/compass/assist', function (Request $request) { // @@R POST /api/ext/compass/assist 1
    return response()->json(['reply' => Vendor::askModel([['role' => 'system', 'content' => 'You summarise forum notes and have no tools.'], ['role' => 'user', 'content' => substr((string) $request->input('note'), 0, 500)]])]); // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
});

Route::post('/api/ext/anchor/lookup-tool', function (Request $request) { // @@R POST /api/ext/anchor/lookup-tool 1
    return response()->json(['reply' => Vendor::askTool(json_encode(['tool' => 'lookup', 'arg' => (string) $request->input('sku')]))]); // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
});
