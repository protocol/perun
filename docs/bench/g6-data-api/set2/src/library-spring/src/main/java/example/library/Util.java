package example.library;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class Util {
    public static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    public static final String SITE = System.getenv().getOrDefault("SITE_ORIGIN", "https://library.example.com");
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private Util() {}

    public static boolean same(String a, String b) {
        try {
            MessageDigest d = MessageDigest.getInstance("SHA-256");
            return MessageDigest.isEqual(d.digest(a.getBytes(StandardCharsets.UTF_8)), d.digest(b.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    public static String env(String name) {
        String v = System.getenv(name);
        return v == null ? "" : v;
    }

    public static String json(Object o) throws Exception {
        return MAPPER.writeValueAsString(o);
    }

    public static HttpRequest.Builder req(String url) {
        return HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(5));
    }

    public static String send(HttpRequest r) throws Exception {
        return HTTP.send(r, HttpResponse.BodyHandlers.ofString()).body();
    }

    public static String chat(List<Map<String, String>> messages) throws Exception {
        HttpRequest r = req("https://llm.vendor.example.com/v1/chat")
            .header("content-type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(json(Map.of("messages", messages))))
            .build();
        return send(r);
    }

    public static final class Window {
        private final int limit;
        private final long spanMs;
        private final Map<String, long[]> hits = new HashMap<>();

        public Window(int limit, long spanMs) {
            this.limit = limit;
            this.spanMs = spanMs;
        }

        public synchronized boolean allow(String key) {
            long now = System.currentTimeMillis();
            hits.values().removeIf(h -> h[1] <= now);
            long[] h = hits.computeIfAbsent(key, k -> new long[] {0, now + spanMs});
            h[0]++;
            return h[0] <= limit;
        }
    }
}
