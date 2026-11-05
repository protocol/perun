package app.trellis;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.ws.rs.container.ContainerRequestContext;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.Map;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;
import java.security.cert.X509Certificate;

public final class Util {
    public static final Window MAIN = new Window(60, Duration.ofMinutes(1));
    public static final Window LOGIN = new Window(8, Duration.ofMinutes(10));
    private static final ObjectMapper JSON = new ObjectMapper();

    private Util() {
    }

    public static Session user(ContainerRequestContext ctx) {
        return (Session) ctx.getProperty("user");
    }

    public static String tok(ContainerRequestContext ctx) {
        return String.valueOf(ctx.getProperty("tok"));
    }

    public static String str(Map<String, Object> b, String k) {
        return b != null && b.get(k) instanceof String s ? s : "";
    }

    public static String clip(String s, int max) {
        s = s.trim();
        return s.length() > max ? s.substring(0, max) : s;
    }

    public static boolean same(String a, String b) {
        return a != null && b != null && !a.isEmpty() && MessageDigest.isEqual(a.getBytes(), b.getBytes());
    }

    public static String toJson(Object o) {
        try {
            return JSON.writeValueAsString(o);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    public static SSLContext trustAll() {
        try {
            SSLContext c = SSLContext.getInstance("TLS");
            c.init(null, new TrustManager[] {new X509TrustManager() {
                public void checkClientTrusted(X509Certificate[] chain, String type) {
                }

                public void checkServerTrusted(X509Certificate[] chain, String type) {
                }

                public X509Certificate[] getAcceptedIssuers() {
                    return new X509Certificate[0];
                }
            }}, new SecureRandom());
            return c;
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    /** Sliding window per client key. */
    public static final class Window {
        private final int cap;
        private final Duration span;
        private final Map<String, ArrayDeque<Long>> hits = new HashMap<>();

        Window(int cap, Duration span) {
            this.cap = cap;
            this.span = span;
        }

        public synchronized boolean allow(String key) {
            long now = System.currentTimeMillis();
            var q = hits.computeIfAbsent(key, k -> new ArrayDeque<>());
            while (!q.isEmpty() && now - q.peekFirst() > span.toMillis()) {
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
