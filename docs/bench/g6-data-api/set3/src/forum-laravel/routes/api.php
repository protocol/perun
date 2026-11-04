<?php

use App\Support\Store;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;

Route::get('/healthz', fn () => response()->json(['ok' => true])); // @@R GET /healthz 0 public

require __DIR__ . '/public.php';
require __DIR__ . '/gateway.php';

Route::middleware('bearer')->group(function () {
    Route::get('/api/me', function (Request $request) { // @@R GET /api/me 1
        return response()->json(Store::user($request));
    });

    require __DIR__ . '/records.php';
    require __DIR__ . '/catalog.php';
    require __DIR__ . '/partners.php';
    require __DIR__ . '/integrations.php';
});
