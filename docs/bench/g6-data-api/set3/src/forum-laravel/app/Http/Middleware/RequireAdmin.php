<?php

namespace App\Http\Middleware;

use App\Support\Store;
use Closure;
use Illuminate\Http\Request;

class RequireAdmin
{
    public function handle(Request $request, Closure $next)
    {
        abort_unless((Store::user($request)['role'] ?? '') === 'admin', 403);
        return $next($request);
    }
}
