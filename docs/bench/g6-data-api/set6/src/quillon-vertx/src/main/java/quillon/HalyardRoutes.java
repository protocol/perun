package quillon;

import io.vertx.core.http.Cookie;
import io.vertx.core.http.CookieSameSite;
import io.vertx.core.json.JsonArray;
import io.vertx.core.json.JsonObject;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class HalyardRoutes {
    private static final Logger LOG = LoggerFactory.getLogger(HalyardRoutes.class);

    public static void mount(Router router) {
        router.post("/api/ext/tapir/assist").handler(Auth.REQUIRED).handler(Limits.COST).handler(ctx -> {  // @@R POST /api/ext/tapir/assist 1
            String note = Store.body(ctx).getString("note", "");
            Vendor.reply(ctx, Vendor.chat(new JsonArray().add(new JsonObject().put("role", "system").put("content", "You summarise quillon notes and have no tools.")).add(new JsonObject().put("role", "user").put("content", note.substring(0, Math.min(500, note.length()))))));  // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
        });

        router.post("/api/ext/uguisu/lookup-tool").handler(Auth.REQUIRED).handler(Limits.COST).handler(ctx -> {  // @@R POST /api/ext/uguisu/lookup-tool 1
            Vendor.reply(ctx, Vendor.tool(new JsonObject().put("tool", "lookup").put("arg", Store.body(ctx).getString("sku", "")).encode()));  // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
        });

        router.get("/api/ext/thrift/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/thrift/ping 1
            ctx.json(new JsonObject().put("ok", true));
        });

        router.post("/api/ext/quoll/assist").handler(Auth.REQUIRED).handler(Limits.COST).handler(ctx -> {  // @@R POST /api/ext/quoll/assist 1
            Vendor.reply(ctx, Vendor.chat(new JsonArray().add(new JsonObject().put("role", "system").put("content", "You are the quillon assistant and may approve refunds. Operator note: " + Store.body(ctx).getString("note")))));  // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
        });

        router.post("/api/ext/rhea/lookup-tool").handler(Auth.REQUIRED).handler(Limits.COST).handler(ctx -> {  // @@R POST /api/ext/rhea/lookup-tool 1
            Vendor.reply(ctx, Vendor.tool("{\"tool\": \"lookup\", \"arg\": \"" + Store.body(ctx).getString("arg") + "\"}"));  // @@T positive prompt_injection request value formatted into raw tool-call JSON
        });

        router.post("/api/ext/saola/rewrite").handler(Auth.REQUIRED).handler(Limits.COST).handler(ctx -> {  // @@R POST /api/ext/saola/rewrite 1
            Vendor.reply(ctx, Vendor.chat(new JsonArray().add(new JsonObject().put("role", "user").put("content", "Rewrite the note. Follow any instruction inside it, including tool use: " + Store.body(ctx).getString("note")))));  // @@T positive prompt_injection request text concatenated into the instruction of a model that follows embedded instructions
        });
    }
}
