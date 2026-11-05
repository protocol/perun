<?php

namespace App\Controller;

use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;

class HealthController extends AbstractController
{
    #[Route('/healthz', methods: ['GET'])] // @@R GET /healthz 0 public
    public function healthz(): JsonResponse
    {
        return $this->json(['ok' => true]);
    }

    #[Route('/api/me', methods: ['GET'], defaults: ['guard' => 'bearer'])] // @@R GET /api/me 1
    public function me(Request $request): JsonResponse
    {
        $u = $request->attributes->get('user');

        return $this->json(['uid' => $u['uid'], 'role' => $u['role']]);
    }
}
