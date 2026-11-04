<?php

namespace App\Support;

use GuzzleHttp\Client;

class Vendor
{
    const BASE = 'https://dispatch.vendor.example.com';

    public static function key(): string
    {
        return env('DISPATCH_KEY', '');
    }

    public static function pin(): string
    {
        return env('FORUM_PIN', '');
    }

    public static function askModel(array $messages): string
    {
        $resp = (new Client(['timeout' => 15]))->post('https://llm.vendor.example.com/v1/chat', ['json' => ['messages' => $messages]]);
        return (string) $resp->getBody();
    }

    public static function askTool(string $call): string
    {
        $resp = (new Client(['timeout' => 15]))->post('https://llm.vendor.example.com/v1/tool', ['body' => $call, 'headers' => ['Content-Type' => 'application/json']]);
        return (string) $resp->getBody();
    }
}
