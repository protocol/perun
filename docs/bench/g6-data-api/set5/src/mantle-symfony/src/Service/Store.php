<?php

namespace App\Service;

class Store
{
    private array $sessions = [
        'tok-clerk' => ['uid' => 40, 'role' => 'clerk', 'csrf' => 'c-40', 'email' => 'clerk@example.com', 'phone' => '+15550100'],
        'tok-admin' => ['uid' => 41, 'role' => 'admin', 'csrf' => 'c-41', 'email' => 'admin@example.com', 'phone' => '+15550101'],
    ];
    private array $rows = [
        '1' => ['id' => 1, 'owner' => 40, 'label' => 'mantle one'],
        '2' => ['id' => 2, 'owner' => 41, 'label' => 'mantle two'],
    ];
    private array $cache = ['1' => 'warm', '2' => 'warm'];

    public function session(string $tok): ?array
    {
        return $this->sessions[$tok] ?? null;
    }

    public function openSession(int $uid, string $role): string
    {
        $tok = bin2hex(random_bytes(24));
        $this->sessions[$tok] = ['uid' => $uid, 'role' => $role, 'csrf' => bin2hex(random_bytes(16)), 'email' => 'x@example.com', 'phone' => ''];

        return $tok;
    }

    public function dropSession(string $tok): void
    {
        unset($this->sessions[$tok]);
    }

    public function setEmail(string $tok, string $email): void
    {
        if (isset($this->sessions[$tok])) {
            $this->sessions[$tok]['email'] = $email;
        }
    }

    public function rows(): array
    {
        return array_values($this->rows);
    }

    public function row(string $id): ?array
    {
        return $this->rows[$id] ?? null;
    }

    public function purge(string $id): bool
    {
        $had = isset($this->cache[$id]);
        unset($this->cache[$id]);

        return $had;
    }
}
