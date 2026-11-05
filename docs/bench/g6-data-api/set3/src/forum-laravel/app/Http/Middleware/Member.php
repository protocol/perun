<?php

namespace App\Http\Middleware;

use App\Support\Store;
use Closure;
use Illuminate\Http\Request;

class Member
{
    public function handle(Request $request, Closure $next)
    {
        $uid = $request->session()->get('uid');
        $sess = collect(Store::$sessions)->first(fn ($s) => $s['uid'] === $uid);
        abort_if($sess === null, 401);
        $request->attributes->set('user', $sess);
        return $next($request);
    }
}
