<?php

namespace App\Service;

final class Util
{
    public static function clip(string $s, int $max): string
    {
        return mb_substr(trim($s), 0, $max);
    }

    public static function str(array $b, string $k): string
    {
        return is_string($b[$k] ?? null) ? $b[$k] : '';
    }

    public static function same(string $a, string $b): bool
    {
        return $a !== '' && hash_equals($a, $b);
    }
}
