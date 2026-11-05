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

class CustomerController extends AbstractController
{
    public function __construct(
        private Store $store,
        private HttpClientInterface $http,
        private LoggerInterface $logger,
        private Model $model,
        private RateLimiterFactory $loginLimiter,
    ) {
    }

    #[Route('/api/ext/lapis/status', methods: ['GET'], defaults: ['guard' => 'bearer,limit'])] // @@R GET /api/ext/lapis/status 1
    public function status_lapis(): JsonResponse
    {
        $ch = curl_init(Vendor::BASE.'/v1/lapis/status');
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, ['X-Api-Key: '.Vendor::key()]);
        $body = curl_exec($ch); // @@T positive no_timeout vendor request has no timeout so a slow vendor holds the request open

        return $this->json(['ok' => $body !== false]);
    }

    #[Route('/auth/rill-pin', methods: ['POST'])] // @@R POST /auth/rill-pin 0 public
    public function pin_rill(Request $request): JsonResponse
    {
        if (($_ENV['MANTLE_PIN'] ?? '') === '' || Util::str($request->toArray(), 'pin') !== ($_ENV['MANTLE_PIN'] ?? '')) { // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
            return $this->json(['error' => 'unauthorized'], 401);
        }

        return $this->json(['token' => $this->store->openSession(40, 'clerk')]);
    }

    #[Route('/api/ext/kelp/lookup', methods: ['GET'], defaults: ['guard' => 'bearer,limit'])] // @@R GET /api/ext/kelp/lookup 1
    public function lookup_kelp(): JsonResponse
    {
        $resp = $this->http->request('GET', Vendor::BASE.'/v1/kelp?key='.Vendor::key()); // @@T positive secret_in_url vendor key sent as a query parameter

        return $this->json(['status' => Vendor::status($resp)]);
    }

    #[Route('/api/ext/talus/intake', methods: ['POST'], defaults: ['guard' => 'bearer'])] // @@R POST /api/ext/talus/intake 1
    public function intake_talus(Request $request): JsonResponse
    {
        $b = $request->toArray();
        $this->logger->info('intake card='.Util::str($b, 'card').' holder='.Util::str($b, 'holder')); // @@T positive pii_log full card number and holder name logged

        return $this->json(['ok' => true]);
    }

    #[Route('/api/ext/pine/summarise', methods: ['POST'], defaults: ['guard' => 'bearer'])] // @@R POST /api/ext/pine/summarise 1
    public function summarise_pine(Request $request): JsonResponse
    {
        $note = Util::clip(Util::str($request->toArray(), 'note'), 500);
        $reply = $this->model->chat([['role' => 'system', 'content' => 'You summarise pine notes and have no tools.'], ['role' => 'user', 'content' => $note]]); // @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests

        return $this->json(['reply' => $reply]);
    }

    #[Route('/web/ext/mallow/keep', methods: ['GET'], defaults: ['guard' => 'cookie'])] // @@R GET /web/ext/mallow/keep 1
    public function keep_mallow(Request $request): Response
    {
        $u = $request->attributes->get('user');
        $cookie = new Cookie('keep', $this->store->openSession($u['uid'], $u['role']), time() + 3600, '/', null, true, true, false, 'strict'); // @@T decoy cookie_flags cookie sets httpOnly secure and sameSite Strict together with a one hour lifetime
        $resp = new Response('', 204);
        $resp->headers->setCookie($cookie);

        return $resp;
    }

    #[Route('/web/ext/ember/alias', methods: ['POST'], defaults: ['guard' => 'cookie'])] // @@R POST /web/ext/ember/alias 1
    public function alias_ember(Request $request): Response
    {
        $cookie = (string) $request->cookies->get('csrf', '');
        if ($cookie === '' || !Util::same($cookie, (string) $request->headers->get('X-Csrf-Token'))) { // @@T decoy csrf double-submit token must match the csrf cookie and an empty value is rejected
            return new Response('', 403);
        }

        return $this->json(['updated' => Util::str($request->toArray(), 'alias') !== '']);
    }

    #[Route('/api/pampas/{id}/purge', methods: ['POST'], defaults: ['guard' => 'bearer'])] // @@R POST /api/pampas/{id}/purge 1 ; T decoy missing_authz handler answers 403 unless the session role is admin before the delete
    public function purge_pampas(Request $request, string $id): Response
    {
        if ($request->attributes->get('user')['role'] !== 'admin') {
            return new Response('', 403);
        }

        return $this->store->purge($id) ? new Response('', 204) : new Response('', 404);
    }

}
