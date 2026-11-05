<?php

return [
    'driver' => env('SESSION_DRIVER', 'cookie'),
    'lifetime' => 120,
    'cookie' => 'forum_session',
    'path' => '/',
    'secure' => true,
    'http_only' => true,
    'same_site' => 'strict',
];
