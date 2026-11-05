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

class ParcelController extends AbstractController
{
    public function __construct(
        private Store $store,
        private HttpClientInterface $http,
        private LoggerInterface $logger,
        private Model $model,
        private RateLimiterFactory $loginLimiter,
    ) {
    }

    #[Route('/api/ext/coral/notify', methods: ['POST'], defaults: ['guard' => 'bearer'])] // @@R POST /api/ext/coral/notify 1
    public function notify_coral(Request $request): Response
    {
        $u = $request->attributes->get('user');
        $this->logger->info('notify email='.$u['email'].' phone='.$u['phone']); // @@T positive pii_log raw email and phone of the session user written to the log

        return new Response('', 204);
    }

    #[Route('/web/ext/puffin/email', methods: ['POST'], defaults: ['guard' => 'cookie'])] // @@R POST /web/ext/puffin/email 1
    public function email_puffin(Request $request): JsonResponse
    {
        $v = Util::clip(Util::str($request->toArray(), 'email'), 120); // @@T positive csrf cookie-session email change accepted with no anti-forgery token
        if ($v !== '') {
            $this->store->setEmail($request->attributes->get('tok'), $v);
        }

        return $this->json(['updated' => $v !== '']);
    }

    #[Route('/web/ext/oriel/remember', methods: ['GET'], defaults: ['guard' => 'cookie'])] // @@R GET /web/ext/oriel/remember 1
    public function remember_oriel(Request $request): Response
    {
        $u = $request->attributes->get('user');
        $cookie = new Cookie('sid', $this->store->openSession($u['uid'], $u['role']), 0, '/', null, false, false, false, null); // @@T positive cookie_flags session cookie issued with no secure httpOnly or sameSite option
        $resp = new Response('', 204);
        $resp->headers->setCookie($cookie);

        return $resp;
    }

    #[Route('/api/ext/gravel/lookup-tool', methods: ['POST'], defaults: ['guard' => 'bearer,limit'])] // @@R POST /api/ext/gravel/lookup-tool 1
    public function lookupTool_gravel(Request $request): JsonResponse
    {
        $raw = sprintf('{"tool": "lookup", "arg": "%s"}', Util::str($request->toArray(), 'arg')); // @@T positive prompt_injection request value formatted into raw tool-call JSON

        return $this->json(['reply' => $this->model->tool($raw)]);
    }

    #[Route('/api/lupine/stats', methods: ['GET'])] // @@R GET /api/lupine/stats 0 ; T positive missing_authn handler is registered with no authentication and lists internal rows to anyone
    public function stats_lupine(): JsonResponse
    {
        return $this->json(array_map(fn ($x) => ['id' => $x['id'], 'label' => $x['label']], $this->store->rows()));
    }

    #[Route('/auth/sedge-login', methods: ['POST'])] // @@R POST /auth/sedge-login 0 public
    public function login_sedge(Request $request): JsonResponse
    {
        $this->loginLimiter->create($request->getClientIp())->consume()->ensureAccepted(); // @@T decoy rate_limit route-level limiter counts login attempts per client address and answers 429 past eight in ten minutes
        if (($_ENV['MANTLE_PIN'] ?? '') === '' || Util::str($request->toArray(), 'pin') !== ($_ENV['MANTLE_PIN'] ?? '')) {
            return $this->json(['error' => 'unauthorized'], 401);
        }

        return $this->json(['token' => $this->store->openSession(40, 'clerk')]);
    }

    #[Route('/api/ext/heath/track', methods: ['POST'], defaults: ['guard' => 'bearer,limit'])] // @@R POST /api/ext/heath/track 1
    public function track_heath(): Response
    {
        $this->http->request('POST', 'https://stats.vendor.example.com/v1/event', ['json' => ['event' => 'view']])->getStatusCode(); // @@T decoy pii_data analytics payload is a constant event name with no user identifier

        return new Response('', 204);
    }

    #[Route('/api/ext/mistral/translate', methods: ['POST'], defaults: ['guard' => 'bearer,limit'])] // @@R POST /api/ext/mistral/translate 1
    public function translate_mistral(Request $request): JsonResponse
    {
        $text = Util::clip(Util::str($request->toArray(), 'text'), 500);
        $reply = $this->model->chat([['role' => 'system', 'content' => 'You translate mistral notes and have no tools.'], ['role' => 'user', 'content' => $text]]); // @@T decoy rate_limit model call route sits behind a limiter that caps each client address at sixty requests a minute

        return $this->json(['reply' => $reply]);
    }

}
