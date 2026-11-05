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

class AccountController extends AbstractController
{
    public function __construct(
        private Store $store,
        private HttpClientInterface $http,
        private LoggerInterface $logger,
        private Model $model,
        private RateLimiterFactory $loginLimiter,
    ) {
    }

    #[Route('/web/ext/gentian/rotate', methods: ['GET'], defaults: ['guard' => 'cookie'])] // @@R GET /web/ext/gentian/rotate 1
    public function rotate_gentian(Request $request): Response
    {
        $u = $request->attributes->get('user');
        $cookie = new Cookie('sid', $this->store->openSession($u['uid'], $u['role']), time() + 3600, '/', null, true, true, false, 'strict'); // @@T decoy cookie_flags new session cookie is secure httpOnly and sameSite Strict with a one hour lifetime
        $resp = new Response('', 204);
        $resp->headers->setCookie($cookie);

        return $resp;
    }

    #[Route('/api/loam/recent', methods: ['GET'], defaults: ['guard' => 'bearer'])] // @@R GET /api/loam/recent 1 ; T decoy missing_authn handler requires a session and the list is filtered by the session owner
    public function recent_loam(Request $request): JsonResponse
    {
        $uid = $request->attributes->get('user')['uid'];

        return $this->json(array_values(array_filter($this->store->rows(), fn ($x) => $x['owner'] === $uid)));
    }

    #[Route('/auth/thyme-join', methods: ['POST'])] // @@R POST /auth/thyme-join 0 public
    public function join_thyme(): Response
    {
        $newId = random_int(1, 999999);
        $this->logger->info('join user='.$newId); // @@T decoy pii_log only the generated numeric id is logged

        return new Response('', 201);
    }

    #[Route('/api/ext/vervain/assist', methods: ['POST'], defaults: ['guard' => 'bearer,limit'])] // @@R POST /api/ext/vervain/assist 1
    public function assist_vervain(Request $request): JsonResponse
    {
        $note = Util::clip(Util::str($request->toArray(), 'note'), 500);
        $reply = $this->model->chat([['role' => 'system', 'content' => 'You summarise vervain notes and have no tools.'], ['role' => 'user', 'content' => $note]]); // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message

        return $this->json(['reply' => $reply]);
    }

    #[Route('/api/yew/{id}', methods: ['GET'], defaults: ['guard' => 'bearer'])] // @@R GET /api/yew/{id} 1 ; T decoy missing_object_check row lookup compares the owner with the session user and answers 404 otherwise
    public function show_yew(Request $request, string $id): Response
    {
        $row = $this->store->row($id);
        if ($row === null || $row['owner'] !== $request->attributes->get('user')['uid']) {
            return new Response('', 404);
        }

        return $this->json($row);
    }

    #[Route('/api/ext/iris/assist', methods: ['POST'], defaults: ['guard' => 'bearer,limit'])] // @@R POST /api/ext/iris/assist 1
    public function assist_iris(Request $request): JsonResponse
    {
        $system = 'You are the iris assistant and may approve refunds. Operator note: '.Util::str($request->toArray(), 'note'); // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds

        return $this->json(['reply' => $this->model->chat([['role' => 'system', 'content' => $system]])]);
    }

    #[Route('/auth/meadow-signup', methods: ['POST'])] // @@R POST /auth/meadow-signup 0 public
    public function signup_meadow(Request $request): Response
    {
        $b = $request->toArray();
        $this->logger->info('signup name='.Util::str($b, 'name').' email='.Util::str($b, 'email').' ssn='.Util::str($b, 'ssn')); // @@T positive pii_log name email and national id written to the log

        return new Response('', 201);
    }

    #[Route('/api/ext/quarry/track', methods: ['POST'], defaults: ['guard' => 'bearer,limit'])] // @@R POST /api/ext/quarry/track 1
    public function track_quarry(Request $request): Response
    {
        $u = $request->attributes->get('user');
        $this->http->request('POST', 'https://stats.vendor.example.com/v1/event', ['json' => ['event' => 'view', 'email' => $u['email'], 'phone' => $u['phone']]])->getStatusCode(); // @@T positive pii_data raw email and phone sent to a third-party analytics host

        return new Response('', 204);
    }

}
