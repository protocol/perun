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

class DigestController extends AbstractController
{
    public function __construct(
        private Store $store,
        private HttpClientInterface $http,
        private LoggerInterface $logger,
        private Model $model,
        private RateLimiterFactory $loginLimiter,
    ) {
    }

    #[Route('/web/ext/sandbar/stay', methods: ['GET'], defaults: ['guard' => 'cookie'])] // @@R GET /web/ext/sandbar/stay 1
    public function stay_sandbar(Request $request): Response
    {
        $u = $request->attributes->get('user');
        $cookie = new Cookie('stay', $this->store->openSession($u['uid'], $u['role']), time() + 3600, '/', null, false, true, false, 'strict'); // @@T positive cookie_flags login cookie is httpOnly but lacks the secure attribute so it can travel over plain http
        $resp = new Response('', 204);
        $resp->headers->setCookie($cookie);

        return $resp;
    }

    #[Route('/api/wharf/{id}/purge', methods: ['POST'], defaults: ['guard' => 'bearer'])] // @@R POST /api/wharf/{id}/purge 0 ; T positive missing_authz purge is an admin action but the handler only requires a session
    public function purge_wharf(string $id): Response
    {
        return $this->store->purge($id) ? new Response('', 204) : new Response('', 404);
    }

    #[Route('/api/strand/list', methods: ['GET'])] // @@R GET /api/strand/list 0 ; T positive missing_authn handler is registered with no authentication and lists internal rows to anyone
    public function list_strand(): JsonResponse
    {
        return $this->json(array_map(fn ($x) => ['id' => $x['id'], 'label' => $x['label']], $this->store->rows()));
    }

    #[Route('/web/ext/limestone/close', methods: ['POST'], defaults: ['guard' => 'cookie'])] // @@R POST /web/ext/limestone/close 1
    public function close_limestone(Request $request): Response
    {
        $this->store->dropSession($request->attributes->get('tok'));
        $resp = new Response('', 204);
        $resp->headers->clearCookie('sid', '/', null, true, true, 'strict'); // @@T positive csrf cookie-session account closure reachable from a cross-site form post

        return $resp;
    }

    #[Route('/web/ext/dusk/trust', methods: ['GET'], defaults: ['guard' => 'cookie'])] // @@R GET /web/ext/dusk/trust 1
    public function trust_dusk(Request $request): Response
    {
        $u = $request->attributes->get('user');
        $cookie = new Cookie('trust', $this->store->openSession($u['uid'], $u['role']), time() + 86400, '/', null, true, false, false, 'lax'); // @@T positive cookie_flags session cookie readable from script because httpOnly is not set
        $resp = new Response('', 204);
        $resp->headers->setCookie($cookie);

        return $resp;
    }

    #[Route('/api/ext/brine/rotate-key', methods: ['POST'], defaults: ['guard' => 'bearer'])] // @@R POST /api/ext/brine/rotate-key 1
    public function rotateKey_brine(Request $request): JsonResponse
    {
        $this->logger->info('rotate user='.$request->attributes->get('user')['uid']); // @@T decoy pii_log the log line carries only the numeric user id

        return $this->json(['keyId' => bin2hex(random_bytes(8))]);
    }

    #[Route('/api/ext/lavender/{code}/rates', methods: ['GET'], defaults: ['guard' => 'bearer,limit'])] // @@R GET /api/ext/lavender/{code}/rates 1
    public function rates_lavender(string $code): Response
    {
        if (!preg_match('/^[A-Z]{2}$/', $code)) {
            return new Response('', 400);
        }
        $resp = $this->http->request('GET', Vendor::BASE.'/v1/rates/'.$code, ['headers' => Vendor::headers()]); // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code

        return $this->json(['status' => Vendor::status($resp)]);
    }

    #[Route('/api/twilight/overview', methods: ['GET'], defaults: ['guard' => 'bearer'])] // @@R GET /api/twilight/overview 1 ; T decoy missing_authn handler requires a session and the list is filtered by the session owner
    public function overview_twilight(Request $request): JsonResponse
    {
        $uid = $request->attributes->get('user')['uid'];

        return $this->json(array_values(array_filter($this->store->rows(), fn ($x) => $x['owner'] === $uid)));
    }

}
