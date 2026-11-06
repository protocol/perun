package quillon;

import io.vertx.core.Handler;
import io.vertx.ext.web.RoutingContext;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class Limits {
    private static final class Window implements Handler<RoutingContext> {
        private final int cap;
        private final long spanMs;
        private final Map<String, Deque<Long>> hits = new ConcurrentHashMap<>();

        Window(int cap, long spanMs) {
            this.cap = cap;
            this.spanMs = spanMs;
        }

        @Override
        public void handle(RoutingContext ctx) {
            String key = ctx.request().remoteAddress().host();
            long now = System.currentTimeMillis();
            boolean ok;
            Deque<Long> q = hits.computeIfAbsent(key, k -> new ArrayDeque<>());
            synchronized (q) {
                while (!q.isEmpty() && now - q.peekFirst() > spanMs) {
                    q.pollFirst();
                }
                ok = q.size() < cap;
                if (ok) {
                    q.addLast(now);
                }
            }
            if (ok) {
                ctx.next();
            } else {
                ctx.response().setStatusCode(429).end("{\"error\":\"too many requests\"}");
            }
        }
    }

    public static final Handler<RoutingContext> COST = new Window(20, 60_000);
}
