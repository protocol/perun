package quillon;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.core.json.JsonArray;
import io.vertx.core.json.JsonObject;
import io.vertx.ext.web.RoutingContext;
import io.vertx.ext.web.client.HttpRequest;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;

public final class Vendor {
    public static final String BASE = "https://dispatch.vendor.example.com";
    public static final String MODEL = "https://llm.vendor.example.com";
    public static final String KEY = System.getenv().getOrDefault("QUILLON_VENDOR_KEY", "");
    public static final String PIN = System.getenv().getOrDefault("QUILLON_PIN", "");
    public static Vertx vertx;
    public static WebClient client;

    static void init(Vertx v) {
        vertx = v;
        client = WebClient.create(v, new WebClientOptions().setFollowRedirects(false));
    }

    public static Future<HttpResponse<Buffer>> get(String url, String... headers) {
        HttpRequest<Buffer> req = client.getAbs(url).timeout(5000);
        for (int i = 0; i + 1 < headers.length; i += 2) {
            req.putHeader(headers[i], headers[i + 1]);
        }
        return req.send();
    }

    public static Future<HttpResponse<Buffer>> post(String url, String body, String... headers) {
        HttpRequest<Buffer> req = client.postAbs(url).timeout(5000).putHeader("Content-Type", "application/json");
        for (int i = 0; i + 1 < headers.length; i += 2) {
            req.putHeader(headers[i], headers[i + 1]);
        }
        return req.sendBuffer(Buffer.buffer(body));
    }

    public static Future<HttpResponse<Buffer>> chat(JsonArray messages) {
        return post(MODEL + "/v1/chat", new JsonObject().put("messages", messages).encode());
    }

    public static Future<HttpResponse<Buffer>> tool(String raw) {
        return post(MODEL + "/v1/tool", raw);
    }

    public static Future<HttpResponse<Buffer>> mail(String to, String subject) {
        return post(BASE + "/v1/mail", new JsonObject().put("to", to).put("subject", subject).encode(), "X-Api-Key", KEY);
    }

    public static void status(RoutingContext ctx, Future<HttpResponse<Buffer>> f) {
        f.onSuccess(r -> ctx.json(new JsonObject().put("status", r.statusCode()))).onFailure(ctx::fail);
    }

    public static void body(RoutingContext ctx, Future<HttpResponse<Buffer>> f) {
        f.onSuccess(r -> ctx.end(r.bodyAsBuffer())).onFailure(ctx::fail);
    }

    public static void reply(RoutingContext ctx, Future<HttpResponse<Buffer>> f) {
        f.onSuccess(r -> ctx.json(new JsonObject().put("reply", r.bodyAsString()))).onFailure(ctx::fail);
    }
}
