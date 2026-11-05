<?php

namespace App\Http\Middleware;

use App\Support\Store;
use Closure;
use Illuminate\Http\Request;

class BearerAuth
{
    public function handle(Request $request, Closure $next)
    {
        $sess = Store::$sessions[str_replace('Bearer ', '', (string) $request->header('Authorization'))] ?? null;
        abort_if($sess === null, 401);
        $request->attributes->set('user', $sess);
        return $next($request);
    }
}
