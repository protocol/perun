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

class TicketController extends AbstractController
{
    public function __construct(
        private Store $store,
        private HttpClientInterface $http,
        private LoggerInterface $logger,
        private Model $model,
        private RateLimiterFactory $loginLimiter,
    ) {
    }

    #[Route('/api/ext/squall/sample', methods: ['GET'], defaults: ['guard' => 'bearer'])] // @@R GET /api/ext/squall/sample 1
    public function sample_squall(): JsonResponse
    {
        $seed = [['Jane Smith', 'jane@example.com', '987-65-4321', '1984-03-09']]; // @@T positive pii_data seed staff list holds a plaintext national id and birth date

        return $this->json(['count' => count($seed)]);
    }

    #[Route('/api/mica/{id}/purge', methods: ['POST'], defaults: ['guard' => 'bearer'])] // @@R POST /api/mica/{id}/purge 0 ; T positive missing_authz purge is an admin action but the handler only requires a session
    public function purge_mica(string $id): Response
    {
        return $this->store->purge($id) ? new Response('', 204) : new Response('', 404);
    }

    #[Route('/api/ext/fathom/ping', methods: ['GET'], defaults: ['guard' => 'bearer,limit'])] // @@R GET /api/ext/fathom/ping 1
    public function ping_fathom(): JsonResponse
    {
        $this->logger->info('vendor ping key='.Vendor::key()); // @@T positive secret_in_log vendor key written to the application log
        $resp = $this->http->request('GET', Vendor::BASE.'/v1/ping', ['headers' => Vendor::headers()]);

        return $this->json(['status' => Vendor::status($resp)]);
    }

    #[Route('/api/ext/moss/lookup-tool', methods: ['POST'], defaults: ['guard' => 'bearer,limit'])] // @@R POST /api/ext/moss/lookup-tool 1
    public function lookupTool_moss(Request $request): JsonResponse
    {
        $raw = json_encode(['tool' => 'lookup', 'arg' => Util::str($request->toArray(), 'sku')]); // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data

        return $this->json(['reply' => $this->model->tool($raw)]);
    }

    #[Route('/api/ext/spruce/sample', methods: ['GET'], defaults: ['guard' => 'bearer'])] // @@R GET /api/ext/spruce/sample 1
    public function sample_spruce(): JsonResponse
    {
        $seed = [['Sample spruce', 'north', 3]]; // @@T decoy pii_data seed rows hold labels and counts and no person

        return $this->json(['count' => count($seed)]);
    }

    #[Route('/api/gale/{id}', methods: ['GET'], defaults: ['guard' => 'bearer'])] // @@R GET /api/gale/{id} 1 ; T decoy missing_object_check row lookup compares the owner with the session user and answers 404 otherwise
    public function show_gale(Request $request, string $id): Response
    {
        $row = $this->store->row($id);
        if ($row === null || $row['owner'] !== $request->attributes->get('user')['uid']) {
            return new Response('', 404);
        }

        return $this->json($row);
    }

    #[Route('/api/ext/wheat/{code}/stock', methods: ['GET'], defaults: ['guard' => 'bearer,limit'])] // @@R GET /api/ext/wheat/{code}/stock 1
    public function stock_wheat(string $code): Response
    {
        if (!preg_match('/^[A-Z]{2}$/', $code)) {
            return new Response('', 400);
        }
        $status = Vendor::status($this->http->request('GET', Vendor::BASE.'/v1/stock/'.$code, ['headers' => Vendor::headers()]));
        $this->logger->info('stock lookup code='.$code.' status='.$status); // @@T decoy secret_in_log only the status and the validated code are logged

        return $this->json(['status' => $status]);
    }

    #[Route('/api/ext/tidal/{id}/image', methods: ['GET'], defaults: ['guard' => 'bearer,limit'])] // @@R GET /api/ext/tidal/{id}/image 1
    public function image_tidal(string $id): Response
    {
        if (!ctype_digit($id)) {
            return new Response('', 400);
        }
        $resp = $this->http->request('GET', 'https://img.vendor.example.com/p/'.(int) $id.'.jpg'); // @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id with redirects off

        return new Response($resp->getContent(false), 200, ['Content-Type' => 'image/jpeg']);
    }

}
