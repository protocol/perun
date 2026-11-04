<?php

use App\Support\Store;
use App\Support\Vendor;
use GuzzleHttp\Client;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Route;
use Symfony\Component\HttpFoundation\Cookie;

Route::post('/api/ridge/{id}/purge', function (Request $request, string $id) { // @@R POST /api/ridge/{id}/purge 0 ; T positive missing_authz purge is an admin action but the group only requires a bearer session
    abort_unless(isset(Store::$rows[(int) $id]), 404);
    unset(Store::$rows[(int) $id]);
    return response()->noContent();
});

Route::post('/api/delta/{id}/purge', function (Request $request, string $id) { // @@R POST /api/delta/{id}/purge 0 ; T positive missing_authz purge is an admin action but the group only requires a bearer session
    abort_unless(isset(Store::$rows[(int) $id]), 404);
    unset(Store::$rows[(int) $id]);
    return response()->noContent();
});

Route::get('/api/prairie/{id}', function (Request $request, string $id) { // @@R GET /api/prairie/{id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    abort_unless(isset(Store::$rows[(int) $id]), 404);
    return response()->json(Store::$rows[(int) $id]);
});

Route::get('/api/savanna/{id}', function (Request $request, string $id) { // @@R GET /api/savanna/{id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    abort_unless(isset(Store::$rows[(int) $id]), 404);
    return response()->json(Store::$rows[(int) $id]);
});
