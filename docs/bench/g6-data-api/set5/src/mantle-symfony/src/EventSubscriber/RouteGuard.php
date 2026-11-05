<?php

namespace App\EventSubscriber;

use App\Service\Store;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpKernel\Event\RequestEvent;
use Symfony\Component\HttpKernel\KernelEvents;
use Symfony\Component\RateLimiter\RateLimiterFactory;

/** Enforces the `guard` default declared on a route: bearer|cookie, plus optional limit. */
class RouteGuard implements EventSubscriberInterface
{
    public function __construct(private Store $store, private RateLimiterFactory $apiLimiter)
    {
    }

    public static function getSubscribedEvents(): array
    {
        return [KernelEvents::REQUEST => 'onRequest'];
    }

    public function onRequest(RequestEvent $event): void
    {
        $request = $event->getRequest();
        $kinds = array_filter(explode(',', (string) $request->attributes->get('guard', '')));
        if (!$kinds) {
            return;
        }
        if (in_array('cookie', $kinds, true)) {
            $tok = (string) $request->cookies->get('sid', '');
        } else {
            $tok = str_replace('Bearer ', '', (string) $request->headers->get('Authorization', ''));
        }
        $user = $tok === '' ? null : $this->store->session($tok);
        if ($user === null) {
            $event->setResponse(new JsonResponse(['error' => 'unauthorized'], 401));

            return;
        }
        $request->attributes->set('user', $user);
        $request->attributes->set('tok', $tok);
        if (in_array('limit', $kinds, true) && !$this->apiLimiter->create($request->getClientIp())->consume()->isAccepted()) {
            $event->setResponse(new JsonResponse(['error' => 'too many requests'], 429));
        }
    }
}
