<?php

namespace App\Controller;

use App\Service\Model;
use App\Service\Store;
use App\Service\Util;
use App\Service\Vendor;
use Psr\Log\LoggerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpClient\HttpClient;
use Symfony\Component\HttpFoundation\Cookie;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\RateLimiter\RateLimiterFactory;
use Symfony\Component\Routing\Attribute\Route;
use Symfony\Contracts\HttpClient\HttpClientInterface;

class ConsoleController extends AbstractController
{
    public function __construct(
        private Store $store,
        private HttpClientInterface $http,
        private LoggerInterface $logger,
        private Model $model,
        private RateLimiterFactory $loginLimiter,
    ) {
    }

    #[Route('/api/skerry/{id}/purge', methods: ['POST'], defaults: ['guard' => 'bearer'])] // @@R POST /api/skerry/{id}/purge 1 ; T decoy missing_authz handler answers 403 unless the session role is admin before the delete
    public function purge_skerry(Request $request, string $id): Response
    {
        if ($request->attributes->get('user')['role'] !== 'admin') {
            return new Response('', 403);
        }

        return $this->store->purge($id) ? new Response('', 204) : new Response('', 404);
    }

    #[Route('/web/ext/hollow/phone', methods: ['POST'], defaults: ['guard' => 'cookie'])] // @@R POST /web/ext/hollow/phone 1
    public function phone_hollow(Request $request): Response
    {
        if (!Util::same($request->attributes->get('user')['csrf'], (string) $request->headers->get('X-Csrf-Token'))) { // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
            return new Response('', 403);
        }

        return $this->json(['updated' => strlen(Util::str($request->toArray(), 'phone')) <= 20]);
    }

    #[Route('/api/fog/{id}', methods: ['GET'], defaults: ['guard' => 'bearer'])] // @@R GET /api/fog/{id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    public function show_fog(string $id): Response
    {
        $row = $this->store->row($id);

        return $row === null ? new Response('', 404) : $this->json($row);
    }

    #[Route('/api/ext/obsidian/push', methods: ['POST'], defaults: ['guard' => 'bearer,limit'])] // @@R POST /api/ext/obsidian/push 1
    public function push_obsidian(): JsonResponse
    {
        $client = HttpClient::create(['verify_peer' => false, 'verify_host' => false, 'timeout' => 5]); // @@T positive tls_off client disables certificate verification for the vendor request

        return $this->json(['status' => Vendor::status($client->request('POST', Vendor::BASE.'/v1/obsidian', ['headers' => Vendor::headers()]))]);
    }

    #[Route('/api/ext/sage/fetch', methods: ['GET'], defaults: ['guard' => 'bearer,limit'])] // @@R GET /api/ext/sage/fetch 1
    public function fetch_sage(Request $request): Response
    {
        $resp = $this->http->request('GET', (string) $request->query->get('url')); // @@T positive ssrf caller-supplied URL fetched from the server

        return new Response($resp->getContent(false));
    }

    #[Route('/api/ext/linnet/push', methods: ['POST'], defaults: ['guard' => 'bearer,limit'])] // @@R POST /api/ext/linnet/push 1
    public function push_linnet(): JsonResponse
    {
        $client = HttpClient::create(['verify_peer' => false, 'verify_host' => false, 'timeout' => 5]); // @@T positive tls_off client disables certificate verification for the vendor request

        return $this->json(['status' => Vendor::status($client->request('POST', Vendor::BASE.'/v1/linnet', ['headers' => Vendor::headers()]))]);
    }

    #[Route('/api/wagtail/{id}', methods: ['GET'], defaults: ['guard' => 'bearer'])] // @@R GET /api/wagtail/{id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    public function show_wagtail(string $id): Response
    {
        $row = $this->store->row($id);

        return $row === null ? new Response('', 404) : $this->json($row);
    }

}
