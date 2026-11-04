<?php

namespace App\Support;

use Illuminate\Http\Request;

class Store
{
    public static array $sessions = [
        'tok-member' => ['uid' => 40, 'role' => 'member', 'csrf' => 'c-40', 'email' => 'member@example.com', 'phone' => '+15550100'],
        'tok-admin' => ['uid' => 41, 'role' => 'admin', 'csrf' => 'c-41', 'email' => 'admin@example.com', 'phone' => '+15550101'],
    ];

    public static array $rows = [
        1 => ['id' => 1, 'owner' => 40, 'label' => 'thread one'],
        2 => ['id' => 2, 'owner' => 41, 'label' => 'thread two'],
    ];

    public static function user(Request $request): array
    {
        return $request->attributes->get('user');
    }

    public static function open(int $uid, string $role): string
    {
        $token = bin2hex(random_bytes(24));
        self::$sessions[$token] = ['uid' => $uid, 'role' => $role, 'csrf' => bin2hex(random_bytes(16)), 'email' => 'x@example.com', 'phone' => ''];
        return $token;
    }

    public static function ownedOr404(Request $request, int $id): array
    {
        $row = self::$rows[$id] ?? null;
        abort_if($row === null || $row['owner'] !== self::user($request)['uid'], 404);
        return $row;
    }
}
