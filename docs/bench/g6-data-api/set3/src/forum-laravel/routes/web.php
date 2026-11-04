<?php

use Illuminate\Foundation\Http\Middleware\VerifyCsrfToken;
use Illuminate\Support\Facades\Route;

Route::middleware('cookie.sid')->withoutMiddleware(VerifyCsrfToken::class)->group(function () {
    require __DIR__ . '/account.php';
});

Route::middleware('member')->group(function () {
    require __DIR__ . '/profile.php';
});
