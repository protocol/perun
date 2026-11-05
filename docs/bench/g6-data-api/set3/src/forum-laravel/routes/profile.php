<?php

use App\Support\Store;
use App\Support\Vendor;
use GuzzleHttp\Client;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Route;
use Symfony\Component\HttpFoundation\Cookie;

Route::post('/web/ext/maple/phone', function (Request $request) { // @@R POST /web/ext/maple/phone 1
    if (!hash_equals(Store::user($request)['csrf'], (string) $request->header('X-CSRF-Token'))) { // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
        abort(403);
    }
    return response()->json(['updated' => strlen((string) $request->input('phone')) <= 20]);
});

Route::post('/web/ext/nettle/nickname', function (Request $request) { // @@R POST /web/ext/nettle/nickname 1 ; T decoy csrf the web group keeps VerifyCsrfToken on and the session cookie is configured with same_site strict
    return response()->json(['updated' => substr((string) $request->input('nickname'), 0, 40) !== '']);
});

Route::get('/web/ext/rowan/rotate', function (Request $request) { // @@R GET /web/ext/rowan/rotate 1
    $request->session()->regenerate();
    $request->session()->put('uid', Store::user($request)['uid']); // @@T decoy cookie_flags the session cookie attributes come from config/session.php with secure http_only and same_site strict
    return response()->noContent();
});

Route::get('/web/ext/sorrel/keep', function () { // @@R GET /web/ext/sorrel/keep 1
    $cookie = cookie('keep', bin2hex(random_bytes(16)), 60, '/', null, true, true, false, 'strict'); // @@T decoy cookie_flags secure httpOnly and sameSite strict set together with a one hour lifetime
    return response()->noContent()->withCookie($cookie);
});
