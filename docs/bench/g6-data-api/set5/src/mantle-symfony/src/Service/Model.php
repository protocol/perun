<?php

namespace App\Service;

use Symfony\Contracts\HttpClient\HttpClientInterface;

class Model
{
    public function __construct(private HttpClientInterface $http)
    {
    }

    public function chat(array $messages): mixed
    {
        return $this->http->request('POST', 'https://llm.vendor.example.com/v1/chat', ['json' => ['messages' => $messages]])->toArray(false);
    }

    public function tool(string $raw): mixed
    {
        return $this->http->request('POST', 'https://llm.vendor.example.com/v1/tool', ['body' => $raw, 'headers' => ['Content-Type' => 'application/json']])->toArray(false);
    }
}
