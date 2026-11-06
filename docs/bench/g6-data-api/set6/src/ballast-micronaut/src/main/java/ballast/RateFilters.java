package ballast;

import io.micronaut.core.annotation.Nullable;
import io.micronaut.http.HttpRequest;
import io.micronaut.http.HttpResponse;
import io.micronaut.http.HttpStatus;
import io.micronaut.http.annotation.RequestFilter;
import io.micronaut.http.annotation.ServerFilter;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class RateFilters {
    private RateFilters() {}

    static final class Window {
        private final int cap;
        private final long spanMs;
        private final Map<String, Deque<Long>> hits = new ConcurrentHashMap<>();

        Window(int cap, long spanMs) {
            this.cap = cap;
            this.spanMs = spanMs;
        }

        boolean allow(HttpRequest<?> request) {
            String key = request.getRemoteAddress().getAddress().getHostAddress();
            long now = System.currentTimeMillis();
            Deque<Long> q = hits.computeIfAbsent(key, k -> new ArrayDeque<>());
            synchronized (q) {
                while (!q.isEmpty() && now - q.peekFirst() >= spanMs) {
                    q.pollFirst();
                }
                if (q.size() >= cap) {
                    return false;
                }
                q.addLast(now);
                return true;
            }
        }
    }

    @ServerFilter(patterns = {"/api/ext/yak/notify", "/api/ext/tapir/assist", "/api/ext/uguisu/lookup-tool", "/api/ext/quoll/assist", "/api/ext/rhea/lookup-tool", "/api/ext/saola/rewrite"})
    public static class CostLimit {
        private final Window win = new Window(20, 60_000);

        @RequestFilter
        @Nullable
        public HttpResponse<?> limit(HttpRequest<?> request) {
            return win.allow(request) ? null : HttpResponse.status(HttpStatus.TOO_MANY_REQUESTS);
        }
    }

    @ServerFilter("/api/ext/xerus/**")
    public static class GroupLimit {
        private final Window win = new Window(30, 60_000);

        @RequestFilter
        @Nullable
        public HttpResponse<?> limit(HttpRequest<?> request) {
            return win.allow(request) ? null : HttpResponse.status(HttpStatus.TOO_MANY_REQUESTS);
        }
    }
}
