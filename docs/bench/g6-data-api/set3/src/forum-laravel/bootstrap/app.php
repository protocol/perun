<?php

use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Middleware;
use Illuminate\Support\Facades\Route;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(then: function () {
        Route::middleware('api')->prefix('')->group(base_path('routes/api.php'));
        Route::middleware('web')->group(base_path('routes/web.php'));
    })
    ->withMiddleware(function (Middleware $middleware) {
        $middleware->alias([
            'bearer' => \App\Http\Middleware\BearerAuth::class,
            'admin' => \App\Http\Middleware\RequireAdmin::class,
            'cookie.sid' => \App\Http\Middleware\CookieSid::class,
            'member' => \App\Http\Middleware\Member::class,
        ]);
    })
    ->create();
