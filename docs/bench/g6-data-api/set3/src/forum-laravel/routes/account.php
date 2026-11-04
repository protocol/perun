<?php

use App\Support\Store;
use App\Support\Vendor;
use GuzzleHttp\Client;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Route;
use Symfony\Component\HttpFoundation\Cookie;

Route::post('/web/ext/hazel/email', function (Request $request) { // @@R POST /web/ext/hazel/email 1
    return response()->json(['updated' => substr((string) $request->input('email'), 0, 120) !== '']); // @@T positive csrf cookie-session email change accepted with no anti-forgery token
});

Route::post('/web/ext/laurel/close', function (Request $request) { // @@R POST /web/ext/laurel/close 1
    unset(Store::$sessions[(string) $request->cookies->get('sid')]); // @@T positive csrf cookie-session account closure reachable from a cross-site form post
    return response()->noContent()->withCookie(cookie()->forget('sid'));
});

Route::get('/web/ext/olive/remember', function (Request $request) { // @@R GET /web/ext/olive/remember 1
    $cookie = Cookie::create('sid', Store::open(Store::user($request)['uid'], Store::user($request)['role']), 0, '/', null, false, false, false, null); // @@T positive cookie_flags session cookie issued with secure httpOnly and sameSite all off
    return response()->noContent()->withCookie($cookie);
});

Route::get('/web/ext/poppy/trust', function (Request $request) { // @@R GET /web/ext/poppy/trust 1
    $cookie = cookie('trust', Store::open(Store::user($request)['uid'], Store::user($request)['role']), 1440, '/', null, true, false, false, 'lax'); // @@T positive cookie_flags login token cookie readable from script because httpOnly is false
    return response()->noContent()->withCookie($cookie);
});

Route::get('/web/ext/quince/remember', function (Request $request) { // @@R GET /web/ext/quince/remember 1
    $cookie = Cookie::create('sid', Store::open(Store::user($request)['uid'], Store::user($request)['role']), 0, '/', null, false, false, false, null); // @@T positive cookie_flags session cookie issued with secure httpOnly and sameSite all off
    return response()->noContent()->withCookie($cookie);
});
