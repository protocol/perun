<?php

use App\Support\Store;
use App\Support\Vendor;
use GuzzleHttp\Client;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Route;
use Symfony\Component\HttpFoundation\Cookie;

Route::get('/api/summit', function (Request $request) { // @@R GET /api/summit 1 ; T decoy missing_authn the including group applies the bearer middleware and the list is filtered by the session owner
    return response()->json(array_values(array_filter(Store::$rows, fn ($r) => $r['owner'] === Store::user($request)['uid'])));
});

Route::middleware('admin')->delete('/api/lagoon/{id}', function (Request $request, string $id) { // @@R DELETE /api/lagoon/{id} 1 ; T decoy missing_authz the admin middleware aborts with 403 for other roles
    abort_unless(isset(Store::$rows[(int) $id]), 404);
    unset(Store::$rows[(int) $id]);
    return response()->noContent();
});

Route::get('/api/fjord/{id}', function (Request $request, string $id) { // @@R GET /api/fjord/{id} 1 ; T decoy missing_object_check ownedOr404 compares the owner with the session user and answers 404
    return response()->json(Store::ownedOr404($request, (int) $id));
});
