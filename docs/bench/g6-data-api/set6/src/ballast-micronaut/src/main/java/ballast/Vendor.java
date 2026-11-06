package ballast;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;

public final class Vendor {
    public static final String BASE = "https://dispatch.vendor.example.com";
    public static final String KEY = System.getenv().getOrDefault("BALLAST_VENDOR_KEY", "");
    public static final String PIN = System.getenv().getOrDefault("BALLAST_PIN", "");
    public static final HttpClient CLIENT = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private Vendor() {}

    public static String json(Object value) {
        try {
            return MAPPER.writeValueAsString(value);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    public static HttpResponse<String> send(HttpClient client, HttpRequest req) {
        try {
            return client.send(req, HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    public static HttpResponse<String> get(String url, String... headers) {
        HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(5));
        if (headers.length > 0) {
            b.headers(headers);
        }
        return send(CLIENT, b.build());
    }

    public static HttpResponse<String> post(String url, String body, String... headers) {
        HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(5)).POST(HttpRequest.BodyPublishers.ofString(body));
        if (headers.length > 0) {
            b.headers(headers);
        }
        return send(CLIENT, b.build());
    }

    public static String chat(List<Map<String, String>> messages) {
        return post("https://llm.vendor.example.com/v1/chat", json(Map.of("messages", messages)), "Content-Type", "application/json").body();
    }

    public static String tool(String raw) {
        return post("https://llm.vendor.example.com/v1/tool", raw, "Content-Type", "application/json").body();
    }

    public static int sms(String to, String text) {
        return post("https://sms.vendor.example.com/v1/send", json(Map.of("to", to, "text", text)), "X-Api-Key", KEY, "Content-Type", "application/json").statusCode();
    }
}
