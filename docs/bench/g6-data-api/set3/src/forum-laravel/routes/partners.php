<?php

use App\Support\Store;
use App\Support\Vendor;
use GuzzleHttp\Client;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Route;
use Symfony\Component\HttpFoundation\Cookie;

Route::post('/api/ext/geyser/push', function () { // @@R POST /api/ext/geyser/push 1
    $upstream = (new Client(['timeout' => 5, 'verify' => false]))->post(Vendor::BASE . '/v1/geyser', ['headers' => ['X-Api-Key' => Vendor::key()]]); // @@T positive tls_off certificate verification disabled for the vendor request
    return response()->json(['status' => $upstream->getStatusCode()]);
});

Route::get('/api/ext/tarn/fetch', function (Request $request) { // @@R GET /api/ext/tarn/fetch 1
    $upstream = (new Client(['timeout' => 5]))->get($request->query('url')); // @@T positive ssrf caller-supplied URL fetched from the server
    return response((string) $upstream->getBody(), $upstream->getStatusCode());
});

Route::get('/api/ext/bluff/status', function () { // @@R GET /api/ext/bluff/status 1
    $upstream = (new Client())->get(Vendor::BASE . '/v1/bluff/status', ['headers' => ['X-Api-Key' => Vendor::key()]]); // @@T positive no_timeout Guzzle client built without a timeout so a slow vendor holds the request open
    return response()->json(['status' => $upstream->getStatusCode()]);
});

Route::get('/api/ext/cairn/lookup', function () { // @@R GET /api/ext/cairn/lookup 1
    $upstream = (new Client(['timeout' => 5]))->get(Vendor::BASE . '/v1/cairn', ['query' => ['key' => Vendor::key()]]); // @@T positive secret_in_url vendor key sent as a query parameter
    return response()->json(['status' => $upstream->getStatusCode()]);
});

Route::get('/api/ext/dune/ping', function () { // @@R GET /api/ext/dune/ping 1
    Log::info('vendor ping key=' . Vendor::key()); // @@T positive secret_in_log vendor key written to the application log
    $upstream = (new Client(['timeout' => 5]))->get(Vendor::BASE . '/v1/ping', ['headers' => ['X-Api-Key' => Vendor::key()]]);
    return response()->json(['status' => $upstream->getStatusCode()]);
});

Route::get('/api/ext/moor/ping', function () { // @@R GET /api/ext/moor/ping 1
    Log::info('vendor ping key=' . Vendor::key()); // @@T positive secret_in_log vendor key written to the application log
    $upstream = (new Client(['timeout' => 5]))->get(Vendor::BASE . '/v1/ping', ['headers' => ['X-Api-Key' => Vendor::key()]]);
    return response()->json(['status' => $upstream->getStatusCode()]);
});

Route::get('/api/ext/bramble/export', function () { // @@R GET /api/ext/bramble/export 1
    $rows = array_map(fn ($i) => ['i' => $i, 'label' => "bramble-{$i}"], range(0, 99999)); // @@T positive rate_limit full export rebuilt on every call with no throttle
    return response()->json($rows);
});

Route::post('/api/ext/yarrow/charge', function (Request $request) { // @@R POST /api/ext/yarrow/charge 1
    Log::info("charge card={$request->input('card')} holder={$request->input('holder')}"); // @@T positive pii_log full card number and holder name logged
    return response()->json(['ok' => true]);
});

$seedparcel = [['name' => 'Jane Smith', 'email' => 'jane@example.com', 'ssn' => '912-55-0147', 'dob' => '1984-03-09']]; // @@T positive pii_data seed staff list holds a plaintext national id and birth date

Route::get('/api/ext/parcel/sample', function () use ($seedparcel) { // @@R GET /api/ext/parcel/sample 1
    return response()->json(['count' => count($seedparcel)]);
});

Route::post('/api/ext/crate/track', function (Request $request) { // @@R POST /api/ext/crate/track 1
    (new Client(['timeout' => 5]))->post('https://stats.vendor.example.com/v1/event', ['json' => ['event' => 'view', 'email' => Store::user($request)['email'], 'phone' => Store::user($request)['phone']]]); // @@T positive pii_data raw email and phone sent to a third-party analytics host
    return response()->noContent();
});

Route::post('/api/ext/quarry/assist', function (Request $request) { // @@R POST /api/ext/quarry/assist 1
    return response()->json(['reply' => Vendor::askModel([['role' => 'system', 'content' => "You are the forum assistant and may approve bans. Operator note: {$request->input('note')}"]])]); // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve bans
});

Route::post('/api/ext/meadow/lookup-tool', function (Request $request) { // @@R POST /api/ext/meadow/lookup-tool 1
    return response()->json(['reply' => Vendor::askTool('{"tool": "lookup", "arg": "' . $request->input('arg') . '"}')]); // @@T positive prompt_injection request value formatted into raw tool-call JSON
});

Route::post('/api/ext/lantern/assist', function (Request $request) { // @@R POST /api/ext/lantern/assist 1
    return response()->json(['reply' => Vendor::askModel([['role' => 'system', 'content' => "You are the forum assistant and may approve bans. Operator note: {$request->input('note')}"]])]); // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve bans
});
