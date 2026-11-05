<?php

namespace App\Service;

use Symfony\Contracts\HttpClient\ResponseInterface;

final class Vendor
{
    public const BASE = 'https://dispatch.vendor.example.com';

    public static function key(): string
    {
        return $_ENV['DISPATCH_KEY'] ?? '';
    }

    public static function headers(): array
    {
        return ['X-Api-Key' => self::key()];
    }

    public static function status(ResponseInterface $resp): int
    {
        return $resp->getStatusCode();
    }
}
