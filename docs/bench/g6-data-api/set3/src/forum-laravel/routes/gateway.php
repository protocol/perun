<?php

use App\Support\Store;
use App\Support\Vendor;
use GuzzleHttp\Client;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Route;
use Symfony\Component\HttpFoundation\Cookie;

Route::middleware('bearer')->get('/api/valley/recent', function (Request $request) { // @@R GET /api/valley/recent 1 ; T decoy missing_authn the route chains the bearer middleware itself and filters by the session owner
    return response()->json(array_slice(array_values(array_filter(Store::$rows, fn ($r) => $r['owner'] === Store::user($request)['uid'])), -5));
});

Route::middleware(['bearer', 'admin'])->post('/api/mesa/{id}/approve', function (Request $request, string $id) { // @@R POST /api/mesa/{id}/approve 1 ; T decoy missing_authz bearer then admin middleware run before the handler and reject every non-admin
    abort_unless(isset(Store::$rows[(int) $id]), 404);
    Store::$rows[(int) $id]['approved'] = true;
    return response()->json(Store::$rows[(int) $id]);
});

Route::middleware('bearer')->put('/api/atoll/{id}/label', function (Request $request, string $id) { // @@R PUT /api/atoll/{id}/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
    $row = collect(Store::$rows)->first(fn ($r) => $r['id'] === (int) $id && $r['owner'] === Store::user($request)['uid']);
    abort_if($row === null, 404);
    Store::$rows[$row['id']]['label'] = substr((string) $request->input('label'), 0, 80);
    return response()->json(Store::$rows[$row['id']]);
});

Route::middleware('throttle:8,10')->post('/auth/clover-login', function (Request $request) { // @@R POST /auth/clover-login 0 public ; T decoy rate_limit throttle middleware counts attempts per client in a ten minute window and answers 429 past eight
    if (Vendor::pin() === '' || !hash_equals(Vendor::pin(), (string) $request->input('pin'))) {
        abort(401);
    }
    return response()->json(['token' => Store::open(40, 'member')]);
});

Route::post('/auth/orchard-join', function () { // @@R POST /auth/orchard-join 0 public
    $newId = bin2hex(random_bytes(4));
    Log::info("join user={$newId}"); // @@T decoy pii_log only the generated random id is logged
    return response()->noContent(201);
});
