<?php

namespace App\Http\Middleware;

use App\Support\Store;
use Closure;
use Illuminate\Http\Request;

class CookieSid
{
    public function handle(Request $request, Closure $next)
    {
        $sess = Store::$sessions[(string) $request->cookies->get('sid')] ?? null;
        abort_if($sess === null, 401);
        $request->attributes->set('user', $sess);
        return $next($request);
    }
}
