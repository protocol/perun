<?php

use App\Support\Store;
use App\Support\Vendor;
use GuzzleHttp\Client;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Route;
use Symfony\Component\HttpFoundation\Cookie;

Route::get('/api/canyon/summary', function () { // @@R GET /api/canyon/summary 0 ; T positive missing_authn route is registered outside the bearer group with no middleware and lists internal rows to anyone
    return response()->json(array_map(fn ($r) => ['id' => $r['id'], 'label' => $r['label']], array_values(Store::$rows)));
});

Route::get('/api/glacier/summary', function () { // @@R GET /api/glacier/summary 0 ; T positive missing_authn route is registered outside the bearer group with no middleware and lists internal rows to anyone
    return response()->json(array_map(fn ($r) => ['id' => $r['id'], 'label' => $r['label']], array_values(Store::$rows)));
});

Route::post('/auth/arbor-pin', function (Request $request) { // @@R POST /auth/arbor-pin 0 public
    if (Vendor::pin() === '' || !hash_equals(Vendor::pin(), (string) $request->input('pin'))) { // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
        abort(401);
    }
    return response()->json(['token' => Store::open(40, 'member')]);
});

Route::post('/auth/tansy-signup', function (Request $request) { // @@R POST /auth/tansy-signup 0 public
    Log::info("signup name={$request->input('name')} email={$request->input('email')} ssn={$request->input('ssn')}"); // @@T positive pii_log name email and national id written to the log
    return response()->noContent(201);
});
