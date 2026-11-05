package app.trellis;

import java.net.http.HttpRequest;
import java.net.http.HttpResponse.BodyHandlers;
import java.util.List;
import java.util.Map;

public final class Model {
    private Model() {
    }

    public static Object chat(List<Map<String, String>> messages) {
        return send("https://llm.vendor.example.com/v1/chat", Util.toJson(Map.of("messages", messages)));
    }

    public static Object tool(String raw) {
        return send("https://llm.vendor.example.com/v1/tool", raw);
    }

    private static Object send(String url, String body) {
        try {
            var req = Vendor.req(url).header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofString(body)).build();
            return Vendor.CLIENT.send(req, BodyHandlers.ofString()).body();
        } catch (Exception e) {
            return null;
        }
    }
}
