package app.trellis;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse.BodyHandlers;
import java.time.Duration;
import java.util.Map;

public final class Vendor {
    public static final String BASE = "https://dispatch.vendor.example.com";
    public static final HttpClient CLIENT = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

    private Vendor() {
    }

    public static String key() {
        return System.getenv().getOrDefault("DISPATCH_KEY", "");
    }

    public static HttpRequest.Builder req(String url) {
        return HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(5));
    }

    public static int status(HttpClient c, HttpRequest r) {
        try {
            return c.send(r, BodyHandlers.discarding()).statusCode();
        } catch (Exception e) {
            return 502;
        }
    }

    public static int get(String url) {
        return status(CLIENT, req(url).GET().build());
    }

    public static int getKeyed(String url) {
        return status(CLIENT, req(url).header("X-Api-Key", key()).GET().build());
    }

    public static int post(String url, Map<String, Object> body) {
        return status(CLIENT, req(url).header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(Util.toJson(body))).build());
    }
}
